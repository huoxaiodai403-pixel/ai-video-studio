"""Volcengine HTTP V3 speech, adapted from Simon's MIT TTS integration.

Audio and word timestamps must come from the same response. Credentials stay
DPAPI-encrypted on this machine; no credentials from the upstream project ship.
"""
import base64
import json
import os
import uuid
import copy
import threading
from contextvars import ContextVar
from pathlib import Path

import requests
import providers
from prompt_library import ROOT

SAVE_LOCK=threading.Lock()
SNAPSHOT=ContextVar('volc_speech_snapshot',default=None)

CONFIG = ROOT/'config/volc-speech.json'
ENDPOINT = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'
DEFAULTS = {'auth_mode': 'api_key', 'app_id': '', 'resource_id': 'seed-tts-2.0',
            'voice': 'zh_female_vv_uranus_bigtts', 'style': ''}


def load(public=False):
    frozen=SNAPSHOT.get()
    row = copy.deepcopy(frozen) if frozen is not None else {**DEFAULTS, **(json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {})}
    if public:
        for name in ('api_key', 'access_token'):
            row['has_'+name] = bool(row.pop(name+'_encrypted', '') or os.getenv('VOLC_TTS_'+name.upper()))
        row['configured'] = bool(row['voice'] and row['resource_id'] and
                                 (row['has_api_key'] if row['auth_mode'] == 'api_key' else row['app_id'] and row['has_access_token']))
    return row


def save(data):
    with SAVE_LOCK:
        return _save(data)


def _save(data):
    if not isinstance(data, dict) or set(data) - {*DEFAULTS, 'api_key', 'access_token', 'clear_api_key', 'clear_access_token'}:
        raise ValueError('火山配置包含未知字段。')
    row = load()
    for name in DEFAULTS:
        if name in data:
            value = data[name]
            if not isinstance(value, str) or len(value) > (500 if name == 'style' else 200):
                raise ValueError('火山配置字段格式不正确：'+name)
            row[name] = value.strip()
    if row['auth_mode'] not in ('api_key', 'legacy'):
        raise ValueError('请选择 API Key 或 App ID + Access Token。')
    for name in ('api_key', 'access_token'):
        secret = data.get(name, '')
        if not isinstance(secret, str) or len(secret) > 4096:
            raise ValueError('凭证格式不正确。')
        if data.get('clear_'+name):
            row.pop(name+'_encrypted', None)
        elif secret.strip():
            row[name+'_encrypted'] = providers.crypt(secret.strip())
    CONFIG.parent.mkdir(exist_ok=True)
    tmp = CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, CONFIG)
    return load(public=True)


def configured():
    row = load()
    headers = {'Content-Type': 'application/json', 'X-Api-Resource-Id': row['resource_id'],
               'X-Api-Connect-Id': str(uuid.uuid4())}
    def secret(name):
        return providers.crypt(row[name+'_encrypted'], True) if row.get(name+'_encrypted') else os.getenv('VOLC_TTS_'+name.upper(), '')
    if row['auth_mode'] == 'api_key':
        key = secret('api_key')
        if not key:
            raise ValueError('请在「在线服务 → 火山引擎」保存 API Key，再生成试听。')
        headers['X-Api-Key'] = key
    else:
        token = secret('access_token')
        if not row['app_id'] or not token:
            raise ValueError('请填写火山 App ID 和 Access Token，或切换新版 API Key 鉴权。')
        headers.update({'X-Api-App-Id': row['app_id'], 'X-Api-Access-Key': token})
    if not row['resource_id'] or not row['voice']:
        raise ValueError('请填写火山资源 ID 和已开通的音色 ID。')
    return row, headers


def objects(raw):
    """Decode NDJSON, SSE, or concatenated objects without splitting JSON strings."""
    decoder, cursor = json.JSONDecoder(), 0
    while cursor < len(raw):
        start = raw.find('{', cursor)
        if start < 0:
            return
        try:
            item, end = decoder.raw_decode(raw, start)
        except json.JSONDecodeError:
            raise ValueError('火山响应不完整，请重试本次试听。') from None
        yield item
        cursor = end


def decode_response(raw):
    audio, words = [], []
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('words'), list):
                words.extend(node['words'])
            for key, value in node.items():
                if key in ('data', 'audio') and isinstance(value, str) and value:
                    try:
                        audio.append(base64.b64decode(value, validate=True))
                    except ValueError:
                        raise ValueError('火山返回了无效音频数据。') from None
                elif key != 'words' and isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    for item in objects(raw):
        code = item.get('code', 0)
        if code not in (0, 20000000):
            raise RuntimeError(f'火山语音错误 {code}。请检查资源 ID、音色授权及额度；服务端未完成合成。')
        walk(item)
    if not audio or not any(audio):
        raise ValueError('火山未返回音频，请检查所选资源与音色是否匹配。')
    # Some responses repeat the same completed sentence's timestamps.
    seen, aligned = set(), []
    for word in words:
        identity = (word.get('word'), word.get('startTime'), word.get('endTime'))
        if identity in seen:
            continue
        seen.add(identity)
        aligned.append({'text': identity[0], 'start': identity[1], 'end': identity[2]})
    return b''.join(audio), aligned


def synthesize(text, mp3, voice, speed):
    row, headers = configured()
    params = {'text': text, 'speaker': voice or row['voice'], 'audio_params': {
        'format': 'mp3', 'sample_rate': 24000, 'bit_rate': 128000,
        'speech_rate': round((speed-1)*100), 'enable_timestamp': True, 'enable_subtitle': True}}
    if row['style']:
        params['additions'] = json.dumps({'context_texts': [row['style']]}, ensure_ascii=False)
    try:
        response = requests.post(ENDPOINT, headers=headers, json={'user': {'uid': 'ai-video-studio'}, 'req_params': params}, timeout=(15, 180))
    except requests.RequestException:
        raise RuntimeError('无法连接火山语音服务，请检查网络后重试；不会自动切换服务或声音。') from None
    if not response.ok:
        tips = {401: '凭证无效或已失效，请重新保存 API Key / Access Token。',
                403: '请检查语音服务是否开通，以及资源 ID、音色授权和账户额度。',
                429: '请求过于频繁或额度受限，请稍后重试并检查控制台。'}
        raise RuntimeError(f'火山语音 HTTP {response.status_code}：'+tips.get(response.status_code, '服务暂时失败，请检查控制台后重试。'))
    audio, words = decode_response(response.text)
    Path(mp3).write_bytes(audio)
    return words

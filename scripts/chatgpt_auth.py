"""Official Sign in with ChatGPT for this local app's text generation.

Uses the public, dynamically registered OAuth client flow and Responses API.
Never reads Codex/Obsidian credentials or exposes OAuth tokens to the browser.
"""
import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from urllib.parse import urlencode

import requests
from filelock import FileLock
import providers
from prompt_library import ROOT

CONFIG = ROOT/'config/chatgpt-account.json'
AUTH = 'https://auth.openai.com/api/accounts/authorize'
TOKEN = 'https://auth.openai.com/api/accounts/oauth/token'
RESOURCE = 'https://api.openai.com/v1'
SCOPE = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
LOCK = threading.RLock()
PENDING = None
GENERATION = 0
LAST_ERROR = ''


def load():
    if not CONFIG.exists():
        return {}
    return json.loads(providers.crypt(json.loads(CONFIG.read_text(encoding='utf-8'))['encrypted'], True))


def save(value):
    CONFIG.parent.mkdir(exist_ok=True)
    temp = CONFIG.with_name('chatgpt-'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps({'encrypted': providers.crypt(json.dumps(value))}), encoding='utf-8')
    temp.replace(CONFIG)


def status():
    with LOCK:
        row = load()
        pending = PENDING and PENDING['expires_at'] > time.time()
        return {'connected': bool(row.get('access_token') and 'chatgpt.tokens.use.direct' in row.get('scopes', [])),
                'email': row.get('email', ''), 'pending': bool(pending),
                'expires_in': max(0, round(PENDING['expires_at']-time.time())) if pending else 0,
                'error': LAST_ERROR, 'capabilities': ['story'],
                'note': '此授权用于文稿与分镜，使用 ChatGPT 套餐额度。媒体生成与转写使用各自的服务。'}


def start(port, new_account=False):
    global PENDING, GENERATION, LAST_ERROR
    with LOCK:
        row = load()
        if not row.get('host_id'):
            row['host_id'] = 'urn:uuid:'+str(uuid.uuid4())
            save(row)
        GENERATION += 1
        verifier = secrets.token_urlsafe(48)
        client = row.get('client_id') if not new_account else None
        PENDING = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32), 'verifier': verifier,
                   'redirect_uri': f'http://127.0.0.1:{port}/auth/chatgpt/callback', 'client_id': client,
                   'subject': row.get('subject') if client else None, 'expires_at': time.time()+600,
                   'generation': GENERATION}
        params = {'client_id': client or 'dynamic_agent_client', 'ext_agent_host_id': row['host_id'],
                  'response_type': 'code', 'redirect_uri': PENDING['redirect_uri'], 'scope': SCOPE,
                  'resource': RESOURCE, 'state': PENDING['state'], 'nonce': PENDING['nonce'],
                  'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
                  'code_challenge_method': 'S256'}
        if not client:
            params['agent_name_hint'] = 'AI Video Studio'
        LAST_ERROR = ''
        return {'authorization_url': AUTH+'?'+urlencode(params), 'expires_in': 600}


def cancel():
    global PENDING, GENERATION, LAST_ERROR
    with LOCK:
        GENERATION += 1
        PENDING = None
        LAST_ERROR = ''
    return {'message': '已取消此次授权；现有账号保持不变。'}


def token_request(data):
    try:
        response = requests.post(TOKEN, data=data, timeout=(15, 30), allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError('无法连接 ChatGPT 授权服务，请检查网络并重新登录。') from None
    try:
        if not response.ok:
            raise RuntimeError(f'ChatGPT 授权未完成（HTTP {response.status_code}），请重新发起登录。')
        try:
            value = response.json()
            if not all(isinstance(value.get(k),str) and value[k] for k in ('access_token','refresh_token')) or not 0<float(value['expires_in'])<31536000:
                raise ValueError()
        except (ValueError,KeyError,TypeError,AttributeError):
            raise ValueError('授权服务未返回完整凭证，请重新登录。') from None
        return value
    finally:
        response.close()


def verify_identity(token, client, nonce):
    import jwt
    jwks = jwt.PyJWKClient('https://auth.openai.com/.well-known/jwks.json', timeout=15)
    try:
        key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256'], audience=client, issuer='https://auth.openai.com',
                            leeway=30, options={'require': ['exp', 'iss', 'aud', 'sub', 'nonce']})
        if not secrets.compare_digest(claims['nonce'], nonce):
            raise ValueError('nonce mismatch')
        return claims
    except Exception:
        raise ValueError('登录身份校验未通过，请关闭授权页后重新登录。') from None


def complete(query):
    global PENDING, LAST_ERROR
    with LOCK:
        pending = PENDING
        if not pending or pending['expires_at'] <= time.time():
            raise ValueError('授权已取消或过期，请回工作台重新登录。')
        if pending.get('processing'):
            raise ValueError('正在完成此次授权，请勿重复提交回调。')
        if any(len(v) != 1 for v in query.values()) or not secrets.compare_digest(query.get('state', [''])[0], pending['state']):
            raise ValueError('授权回调不匹配，请回工作台重新登录。')
        if query.get('error'):
            PENDING = None
            LAST_ERROR = '你未完成账号授权，现有账号保持不变。'
            raise ValueError(LAST_ERROR)
        client = query.get('client_id', [pending['client_id']])[0]
        if not isinstance(client, str) or not client.startswith('oaiapp_') or (pending['client_id'] and client != pending['client_id']):
            raise ValueError('授权返回的应用注册信息不一致。')
        code = query.get('code', [''])[0]
        if not code or len(code) > 4096:
            raise ValueError('授权码缺失或格式错误。')
        # Consume this callback once; cancellation still advances GENERATION.
        PENDING['processing'] = True
        row = load()
        if not row.get('access_token'):
            row['client_id'] = client
            save(row)
    try:
        tokens = token_request({'grant_type': 'authorization_code', 'client_id': client, 'code': code,
                                'code_verifier': pending['verifier'], 'redirect_uri': pending['redirect_uri'], 'resource': RESOURCE})
        identity = verify_identity(tokens.get('id_token', ''), client, pending['nonce'])
        if pending['subject'] and identity['sub'] != pending['subject']:
            raise ValueError('授权账号与原账号不同，请使用「更换账号」重新连接。')
        scopes = tokens.get('scope', '').split()
        if 'chatgpt.tokens.use.direct' not in scopes:
            raise ValueError('账号已识别，但未获得 ChatGPT 套餐使用授权。请检查账号资格与授权选项。')
        with LOCK:
            if pending['generation'] != GENERATION:
                raise ValueError('此次登录已取消，不会保存迟到的授权结果。')
            record = {'host_id': row['host_id'], 'client_id': client, 'subject': identity['sub'],
                      'email': identity.get('email', ''), 'access_token': tokens['access_token'],
                      'refresh_token': tokens['refresh_token'], 'id_token': tokens['id_token'], 'scopes': scopes,
                      'expires_at': time.time()+float(tokens['expires_in'])}
            save(record)
            PENDING = None
            LAST_ERROR = ''
        return status()
    except Exception as exc:
        with LOCK:
            if pending['generation'] == GENERATION:
                PENDING = None
                LAST_ERROR = str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '无法保存账号授权，请检查本机配置权限。'
        raise


def access(force=False):
    CONFIG.parent.mkdir(exist_ok=True)
    with FileLock(str(CONFIG.with_suffix('.refresh.lock')), timeout=40), LOCK:
        row = load()
        if not row.get('access_token') or 'chatgpt.tokens.use.direct' not in row.get('scopes', []):
            raise ValueError('请先在「在线服务 → 编剧与分镜」登录并授权 ChatGPT。')
        if force or row.get('expires_at', 0) < time.time()+60:
            tokens = token_request({'grant_type': 'refresh_token', 'client_id': row['client_id'],
                                    'refresh_token': row['refresh_token'], 'resource': RESOURCE})
            row.update(access_token=tokens['access_token'], refresh_token=tokens['refresh_token'],
                       scopes=tokens.get('scope', ' '.join(row['scopes'])).split(),
                       expires_at=time.time()+float(tokens['expires_in']))
            if 'chatgpt.tokens.use.direct' not in row['scopes']:
                raise ValueError('ChatGPT 套餐授权已变更，请重新登录。')
            save(row)
        return row['access_token']


def request(method, path, **kwargs):
    for attempt in range(2):
        token = access(force=attempt > 0)
        try:
            response = requests.request(method, RESOURCE+path, headers={'Authorization': 'Bearer '+token}, timeout=(15, 180), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise RuntimeError('ChatGPT 连接失败，请检查网络。') from None
        if response.status_code == 401 and attempt == 0:
            response.close()
            continue
        if not response.ok:
            status_code = response.status_code
            response.close()
            raise RuntimeError('ChatGPT 套餐额度或请求频率受限，请查看账号使用情况。' if status_code == 429 else f'ChatGPT 请求失败（HTTP {status_code}），请检查授权与模型权限。')
        return response
    raise RuntimeError('ChatGPT 账号需要重新登录。')


def models():
    response = request('GET', '/models')
    try:
        return [{'id': r['slug'], 'name': r.get('display_name', r['slug'])} for r in response.json().get('models', [])
                if r.get('visibility') == 'list' and isinstance(r.get('slug'), str)]
    except (requests.RequestException,ValueError):
        raise RuntimeError('ChatGPT 返回中断或格式无效，请检查连接后重试。') from None
    finally:
        response.close()


def generate(model, messages):
    if not model or model not in {r['id'] for r in models()}:
        raise ValueError('请先选择当前 ChatGPT 账号实际可用的模型。')
    response = request('POST', '/responses', json={'model': model, 'input': messages, 'store': False, 'stream': True}, stream=True)
    output, completed = [], False
    try:
        for line in response.iter_lines():
            if not line.startswith(b'data:'):
                continue
            raw = line[5:].strip()
            if raw == b'[DONE]':
                continue
            event = json.loads(raw)
            if event.get('type') == 'response.output_text.delta':
                output.append(event.get('delta', ''))
            elif event.get('type') == 'response.completed':
                completed = True
            elif event.get('type') in ('response.failed', 'response.incomplete', 'error'):
                raise RuntimeError('ChatGPT 未完成生成，请检查套餐额度、账号授权或稍后重试。')
    except (requests.RequestException,ValueError):
        raise RuntimeError('ChatGPT 返回中断或格式无效，请检查连接后重试。') from None
    finally:
        response.close()
    if not completed or not ''.join(output).strip():
        raise RuntimeError('ChatGPT 返回中断或缺少完成确认，未将部分文本当作成功结果。')
    return ''.join(output)


def logout():
    global GENERATION, PENDING, LAST_ERROR
    with LOCK:
        row = load()
        GENERATION += 1
        PENDING = None
        LAST_ERROR = ''
        confirmed = not row.get('refresh_token')
        if row.get('refresh_token'):
            try:
                metadata = requests.get('https://auth.openai.com/.well-known/openid-configuration', timeout=10).json()
                endpoint = metadata.get('revocation_endpoint', '')
                if endpoint.startswith('https://auth.openai.com/'):
                    confirmed = requests.post(endpoint, data={'token': row['refresh_token'], 'token_type_hint': 'refresh_token', 'client_id': row['client_id']}, timeout=15, allow_redirects=False).status_code == 200
            except (requests.RequestException,ValueError,TypeError,AttributeError):
                pass
        save({k: v for k, v in row.items() if k in ('host_id', 'client_id', 'subject', 'email')})
    return {'message': '已断开此工作台账号连接。' if confirmed else '本机凭证已清除；未确认远端撤销，请在 ChatGPT 设置中断开此应用。'}

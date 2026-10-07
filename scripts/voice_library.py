"""Local voice presets backed by registered reference audio, never arbitrary paths."""
import copy
import hashlib
import json
import os
import re
import threading
import uuid
import shutil
import wave
from pathlib import Path
from urllib.parse import quote

from filelock import FileLock
import creation_settings as settings

ROOT = settings.ROOT
PRESETS = ROOT / 'config/voice-presets.json'
LOCK = threading.RLock()
AUDIO_SUFFIXES = {'.wav', '.mp3', '.m4a', '.flac'}


def _label(value, name, maximum, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value.strip()) > maximum:
        raise ValueError(f'{name}应为 {0 if empty else 1}–{maximum} 字')
    if any(ord(char) < 32 for char in value):
        raise ValueError(f'{name}不能包含换行或控制字符')
    return value.strip()


def role_name(value):
    name = _label(value, '角色名称', 32)
    if not re.fullmatch(r'[\w\u4e00-\u9fff· -]+', name) or name.casefold() in {'__proto__', 'prototype', 'constructor'}:
        raise ValueError('角色名称只允许中英文、数字、空格、下划线、短横线和间隔号')
    return name


def preset_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('请选择音色列表中的预设')
    return value


def _reference_id(path):
    return hashlib.sha256(str(path.resolve()).casefold().encode('utf-8')).hexdigest()[:24]


def references():
    """Only direct library children are exposed; raw downloaded sources stay private."""
    found = {}
    for folder in (ROOT / 'apps/index-tts/examples', ROOT / 'assets/voices'):
        root = folder.resolve()
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            path = entry.resolve()
            if (not path.is_relative_to(root) or not path.is_file() or
                    path.suffix.lower() not in AUDIO_SUFFIXES or entry.name.startswith('emo_')):
                continue
            if root.name == 'examples' and not re.fullmatch(r'voice_\d+\.wav', entry.name, re.I):
                continue
            rid = _reference_id(path)
            found[rid] = {'id': rid, 'path': str(path), 'name': entry.stem,
                          'preview_url': '/api/voice-library/audio?ref=' + quote(rid)}
    return list(found.values())


def validate_reference(value, known=None):
    if not isinstance(value, str):
        raise ValueError('请选择已登记的参考音频')
    candidate = Path(value)
    if not candidate.is_absolute():
        raise ValueError('参考音频必须来自音色库')
    resolved = candidate.resolve()
    rows = references() if known is None else known
    if not any(resolved == Path(row['path']) for row in rows):
        raise ValueError('参考音频不在已登记的音色库中，请先上传参考音频')
    return str(resolved)


def validate_voice(value, known=None):
    if not isinstance(value, dict) or set(value) - set(settings.DEFAULTS['voice']):
        raise ValueError('音色参数格式不正确')
    merged = settings.merge(settings.DEFAULTS['voice'], value)
    if merged.get('reference') or merged['engine'] in ('index-tts','qwen3-clone'):
        merged['reference'] = validate_reference(merged['reference'], known)
    if merged.get('prosody_reference'):
        merged['prosody_reference'] = validate_reference(merged['prosody_reference'], known)
    return settings.validate_voice(merged)


def _document():
    if not PRESETS.exists():
        return {'version': 1, 'presets': []}
    content = json.loads(PRESETS.read_text(encoding='utf-8-sig'))
    if not isinstance(content, dict) or content.get('version') != 1 or not isinstance(content.get('presets'), list):
        raise ValueError('音色预设配置格式不正确，请检查 config/voice-presets.json')
    if len(content['presets']) > 200:
        raise ValueError('音色预设数量超过 200 个')
    ids = [preset_id(row.get('id')) for row in content['presets'] if isinstance(row, dict)]
    if len(ids) != len(content['presets']) or len(set(ids)) != len(ids):
        raise ValueError('音色预设配置包含重复或无效记录')
    if content.get('default_preset_id') is not None:
        preset_id(content['default_preset_id'])
    return content


def _write_document(document):
    temporary = PRESETS.with_name('voice-presets-' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, PRESETS)
    finally:
        temporary.unlink(missing_ok=True)


def _record(value, identity, known):
    if not isinstance(value, dict):
        raise ValueError('预设必须是 JSON 对象')
    tags = value.get('tags', [])
    if not isinstance(tags, list) or len(tags) > 8:
        raise ValueError('题材标签最多 8 个')
    tags = list(dict.fromkeys(_label(tag, '题材标签', 20) for tag in tags))
    if not isinstance(value.get('voice'), dict) or 'reference' not in value['voice']:
        raise ValueError('保存音色预设必须选择已登记的参考音频')
    return {'id': preset_id(identity), 'name': _label(value.get('name'), '音色名称', 60),
            'tags': tags, 'description': _label(value.get('description', ''), '音色说明', 240, empty=True),
            'voice': validate_voice(value['voice'], known)}


def _catalog():
    refs = references()
    reference_map = {row['path']: row for row in refs}
    presets = {}
    for reference in refs:
        path = Path(reference['path'])
        example = path.parent == (ROOT / 'apps/index-tts/examples').resolve()
        match = re.fullmatch(r'voice_(\d+)', path.stem, re.I) if example else None
        identity = 'builtin-voice-' + match.group(1) if match else 'reference-' + reference['id']
        voice = validate_voice({'reference': str(path)}, refs)
        presets[identity] = {'id': identity, 'name': '示例音色 ' + match.group(1) if match else path.stem,
                             'tags': ['示例'] if example else ['已导入'],
                             'description': 'IndexTTS 随附参考音频，请试听后选择适合的题材。' if example else '已有参考音频；可试听并另存题材预设。',
                             'voice': voice, 'preview_url': reference['preview_url'], 'source': 'builtin' if example else 'reference'}
    document = _document()
    for saved in document['presets']:
        row = _record(saved, saved['id'], refs)
        row.update(preview_url=reference_map.get(row['voice']['reference'],{}).get('preview_url'), source='saved')
        presets[row['id']] = row
    current = settings.load()['voice']
    saved_default = presets.get(document.get('default_preset_id'))
    default_id = saved_default['id'] if saved_default and saved_default['voice'] == current else next(
        (row['id'] for row in reversed(list(presets.values())) if row['voice'] == current), None)
    return {'presets': list(presets.values()), 'references': refs, 'emotions': list(settings.EMOTIONS),
            'default_preset_id': default_id, 'default_voice': copy.deepcopy(current)}


def catalog():
    with LOCK:
        return _catalog()


def resolve(identity, catalog_data=None):
    identity = preset_id(identity)
    data = catalog() if catalog_data is None else catalog_data
    row = next((row for row in data['presets'] if row['id'] == identity), None)
    if row is None:
        raise ValueError('音色预设不存在，请刷新音色列表后重新选择')
    # Return an owned copy so a job snapshot can never mutate the live preset.
    return copy.deepcopy(row)


def save(value):
    if not isinstance(value, dict) or set(value) - {'id', 'name', 'tags', 'description', 'voice'}:
        raise ValueError('预设字段格式不正确')
    with LOCK:
        PRESETS.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(PRESETS) + '.lock', timeout=5):
            data = _catalog()
            supplied_id = value.get('id')
            editing = supplied_id not in (None, '')
            identity = preset_id(supplied_id) if editing else 'voice-' + uuid.uuid4().hex[:16]
            if editing:
                resolve(identity, data)
            row = _record(value, identity, data['references'])
            document = _document()
            rows = document['presets']
            rows = [entry for entry in rows if entry['id'] != identity] + [row]
            if len(rows) > 200:
                raise ValueError('最多保存 200 个音色预设')
            document['presets'] = rows
            _write_document(document)
            return resolve(identity)


def set_default(identity):
    with LOCK:
        PRESETS.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(PRESETS) + '.lock', timeout=5):
            row = resolve(identity)
            # Preserve non-voice configuration and the chosen identity among equal presets.
            settings.save({'voice': copy.deepcopy(row['voice'])})
            document = _document()
            document['default_preset_id'] = row['id']
            _write_document(document)
            return row


def audio_path(identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{24}', identity):
        raise ValueError('无效的音色试听标识')
    row = next((row for row in references() if row['id'] == identity), None)
    if row is None:
        raise FileNotFoundError('参考音频不存在')
    return Path(row['path'])


def from_speech(value):
    """Freeze a successful designed voice into a reusable clone reference."""
    if not isinstance(value,dict) or set(value)-{'job_id','name','tags','description'}:
        raise ValueError('保存试听的参数格式不正确')
    job=value.get('job_id')
    if not isinstance(job,str) or not re.fullmatch(r'speech-[a-f0-9]{10}',job):raise ValueError('请选择已成功的配音任务')
    name=_label(value.get('name'),'音色名称',60)
    description=_label(value.get('description',''),'音色说明',240,empty=True)
    tags=value.get('tags',[])
    if not isinstance(tags,list) or len(tags)>8:raise ValueError('题材标签最多8个')
    tags=list(dict.fromkeys(_label(tag,'题材标签',20) for tag in tags))
    base=(ROOT/'projects/studio').resolve()
    project=(base/job).resolve()
    if not project.is_relative_to(base) or not project.is_dir():raise ValueError('配音任务路径无效')
    def task_file(relative):
        path=(project/relative).resolve()
        if not path.is_relative_to(project) or not path.is_file():raise ValueError('配音任务文件缺失或越界')
        return path
    status=json.loads(task_file('status.json').read_text(encoding='utf-8'))
    if status.get('status')!='done' or status.get('kind')!='speech' or status.get('backend')!='local':
        raise ValueError('请选择已经完成的本地配音任务')
    spec=json.loads(task_file('storyboard.json').read_text(encoding='utf-8'))
    scenes=spec.get('scenes')
    if not isinstance(scenes,list) or len(scenes)!=1 or scenes[0].get('id')!='preview':
        raise ValueError('固定角色需要单段声音设计试听')
    transcript=scenes[0].get('narration')
    if not isinstance(transcript,str) or not 1<=len(transcript.strip())<=2000:
        raise ValueError('声音设计试听原文无效')
    voice=settings.validate_voice(settings.voice_for(spec,scenes[0]))
    if voice['engine']!='qwen3-design':raise ValueError('固定角色保存用于声音设计试听，其他音色可直接保存参数预设')
    source=task_file('audio/preview.wav')
    with wave.open(str(source)) as audio:
        duration=audio.getnframes()/audio.getframerate()
    if not 2<=duration<=30:raise ValueError('固定角色需要2至30秒清晰短句，请用较短台词重新设计试听')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    audio_metadata=json.loads(task_file('audio/preview.json').read_text(encoding='utf-8'))
    if (audio_metadata.get('engine')!='qwen3-design' or audio_metadata.get('text')!=transcript
            or not isinstance(audio_metadata.get('voice'),dict)
            or settings.validate_voice(audio_metadata['voice'])!=voice):
        raise ValueError('试听引擎、原文或音色参数与生成记录不符，请重新生成')
    if audio_metadata.get('audio_sha256')!=digest:raise ValueError('试听文件与生成记录不符，请重新生成')
    destination=ROOT/'assets/voices'/('designed-'+digest[:24]+'.wav')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.resolve().is_relative_to(destination.parent.resolve()):raise ValueError('参考音频路径越界')
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest()!=digest:raise ValueError('参考文件校验失败')
    if not destination.exists():shutil.copy2(source,destination)
    voice.update(engine='qwen3-clone',reference=str(destination),qwen_ref_text=transcript,
                 qwen_instruct='',speed=1.0,pitch_semitones=0.0,formant_shift=1.0,
                 duration_factor=1.0,prosody_reference='')
    return save({'name':name,'tags':tags,'description':description,'voice':voice})

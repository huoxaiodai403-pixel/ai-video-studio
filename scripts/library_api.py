"""Read-only catalog of workbench deliverables and explicitly registered assets."""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlparse
import uuid
import wave

from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.RLock()
HASH_CACHE = {}
WORKFLOWS = {'image', 'video', 'speech', 'motion', 'whiteboard', 'investigation', 'enhance', 'asr', 'story', 'music', 'sfx', 'generation'}
STATUSES = {'done', 'queued', 'running', 'error', 'draft', 'preview'}
MEDIA_TYPES = {'image', 'video', 'audio', 'document'}
SUFFIXES = {'image': {'.png', '.jpg', '.jpeg', '.webp', '.gif'}, 'video': {'.mp4', '.mov', '.mkv', '.webm', '.m4v'},
            'audio': {'.wav', '.mp3', '.m4a', '.flac'}, 'document': {'.srt', '.json', '.md', '.zip', '.csv', '.txt', '.excalidraw', '.html', '.blend'}}
LABELS = {'image': '插画', 'video': '成片', 'speech': '配音', 'motion': '动态镜头', 'whiteboard': '白板视频',
          'investigation': '热点长片', 'enhance': '画质增强', 'asr': '字幕转写', 'story': '小说分镜',
          'music': '配乐', 'sfx': '音效', 'generation': '生成工坊'}


def _read(path, default=None):
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or path.stat().st_size > 4 * 1024 * 1024:
            return default
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def _id(namespace, key):
    return 'lib-' + hashlib.sha256((namespace + ':' + key).encode('utf-8')).hexdigest()[:24]


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _text(value, maximum=200):
    return ''.join(char for char in value if ord(char) >= 32).strip()[:maximum] if isinstance(value, str) else ''


def _url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return ''
    try:
        parsed = urlparse(value)
        return value if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else ''
    except ValueError:
        return ''


def _file(folder, relative, media_type):
    """Only registered media types contained in this exact owner directory."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '\\' in relative:
        return None
    try:
        base = folder.resolve()
        path = (base / relative).resolve()
        if (not base.is_relative_to(ROOT.resolve()) or not path.is_relative_to(base)
                or not path.is_file() or path.suffix.lower() not in SUFFIXES[media_type]):
            return None
        return path
    except (OSError, ValueError):
        return None


def _output(path):
    return '/outputs/' + quote(path.relative_to((ROOT / 'projects/studio').resolve()).as_posix(), safe='/')


def _image_hash(path):
    """Cache small-image digests by actual file identity; never hash full films on GET."""
    stamp = path.stat()
    key = (str(path), stamp.st_size, stamp.st_mtime_ns)
    with LOCK:
        if key not in HASH_CACHE:
            if len(HASH_CACHE) > 1000:
                HASH_CACHE.clear()
            with path.open('rb') as stream:
                HASH_CACHE[key] = hashlib.file_digest(stream, 'sha256').hexdigest()
        return HASH_CACHE[key]


def _geometry(path, media_type, hints):
    result = {key: None for key in ('duration_seconds', 'width', 'height')}
    for source in hints:
        if not isinstance(source, dict) or source.get('estimated_duration'):
            continue
        for key, aliases in [('duration_seconds', ('duration_seconds', 'duration')), ('width', ('width', 'native_width')),
                             ('height', ('height', 'native_height'))]:
            for alias in aliases:
                value = _number(source.get(alias))
                if result[key] is None and value is not None:
                    result[key] = value
    if path:
        try:
            if media_type == 'image':
                from PIL import Image
                with Image.open(path) as image:
                    result.update(width=image.width, height=image.height)
            elif path.suffix.lower() == '.wav':
                with wave.open(str(path)) as audio:
                    result['duration_seconds'] = audio.getnframes() / audio.getframerate()
        except (OSError, ValueError, wave.Error):
            pass  # Retain the known metadata; cataloging never runs inference or ffprobe.
    return result


def _row(identity, workflow, media_type, title, created, status, project, path=None, **extra):
    url = _output(path) if path and path.is_relative_to((ROOT / 'projects/studio').resolve()) else None
    return {'id': identity, 'kind': workflow, 'type': workflow, 'workflow': workflow, 'media_type': media_type,
            'title': title, 'created_at': created, 'status': status, 'job_status': status,
            'preview_url': url, 'download_url': url, 'project_id': project, 'source_tool': workflow,
            'source_url': '', 'provenance_url': '', 'thumbnail_url': None, 'deliverables': [],
            'absolute_path': str(path) if path else None,
            'size_bytes': path.stat().st_size if path else None, 'duration_seconds': None,
            'width': None, 'height': None, 'favorite': False, 'tags': [], **extra}


def _deliverables(folder, primary, kind):
    result = [{'label': '主要作品', 'url': _output(primary), 'kind': kind}] if primary else []
    associated = [('subtitles.srt', '字幕', 'subtitle'), ('transcription.json', '识别正文', 'transcript'),
                  ('storyboard.json', '完整分镜', 'storyboard'), ('script.md', '文稿', 'script'),
                  ('sources.csv', '来源台账', 'sources'), ('publish-copy.md', '发布文案', 'publishing'),
                  ('delivery.zip', '交付包', 'bundle'), ('chapters.txt', '章节时间', 'chapters')]
    associated.extend([('plan.json', '创作计划', 'plan'), ('qa.json', '生成检查记录', 'qa'),
                       ('scene.html', '可编辑动画源码', 'source'), ('scene.blend', '可编辑三维场景', 'source'),
                       ('scene-spec.json', '三维场景参数', 'source'), ('timeline.json', '镜头时间轴', 'timeline')])
    state = _read(folder / 'status.json', {})
    whiteboard = folder.name.startswith('whiteboard-') or isinstance(state, dict) and state.get('kind') == 'whiteboard'
    if whiteboard:
        associated.extend([('旁白稿.md', '旁白稿', 'script'), ('发布.md', '发布文案', 'publishing')])
    for relative, label, item_kind in associated:
        path = _file(folder, relative, 'document')
        if path and path != primary:
            result.append({'label': label, 'url': _output(path), 'kind': item_kind})
    sources = state.get('sources', []) if isinstance(state, dict) else []
    if whiteboard and isinstance(sources, list):
        seen = set()
        prefix = '/outputs/' + folder.name + '/'
        for source in sources[:200]:
            if not isinstance(source, str):
                continue
            try:
                parsed = urlparse(source)
            except ValueError:
                continue
            decoded = unquote(parsed.path)
            if parsed.scheme or parsed.netloc or parsed.params or parsed.query or parsed.fragment or not decoded.startswith(prefix):
                continue
            relative = decoded[len(prefix):]
            match = re.fullmatch(r'(sources)/([\w-]+\.excalidraw)|(scenes)/([\w-]+\.excalidraw\.md)', relative)
            if not match:
                continue
            subdir, name = (match[1], match[2]) if match[1] else (match[3], match[4])
            source_root = folder / subdir
            if not source_root.resolve().is_relative_to(folder.resolve()):
                continue
            path = _file(source_root, name, 'document')
            if path and path not in seen:
                seen.add(path)
                label = name.removesuffix('.md').removesuffix('.excalidraw')
                result.append({'label': '可编辑白板 · ' + label, 'url': _output(path), 'kind': 'excalidraw'})
    for relative in ('封面-4x3.png', '封面-3x4.png', 'cover-4x3.png', 'cover-3x4.png', 'cover-landscape.png', 'cover.png'):
        path = _file(folder, relative, 'image')
        if path:
            result.append({'label': '封面 · ' + path.stem, 'url': _output(path), 'kind': 'cover'})
    return result


def _workflow(job, state):
    kind = state.get('kind')
    if kind == 'music':
        return 'sfx' if state.get('engine') == 'stable-audio-3-sfx' else 'music'
    if isinstance(kind, str) and kind in WORKFLOWS:
        return kind
    prefix = job.split('-')[0]
    if prefix in WORKFLOWS:
        return prefix
    if 'image' in state or re.fullmatch(r'[a-f0-9]{12}', job):
        return 'image'
    return None


def _product(job, state, folder):
    workflow = _workflow(job, state)
    if not workflow:
        return None
    if workflow == 'generation' and state.get('operation') == 'draft' and state.get('status') == 'done':
        return None  # The saved parent plan owns this draft; the writing job is only execution history.
    spec = _read(folder / 'storyboard.json', {}) if folder else {}
    if workflow == 'generation' and job.startswith('gen-') and folder:
        spec = _read(folder/'plan.json', {})
    prompt = _read(folder / 'prompt.json', {}) if folder else {}
    request = _read(folder / 'request.json', {}) if folder else {}
    spec, prompt, request = [value if isinstance(value, dict) else {} for value in (spec, prompt, request)]
    media_type = 'image' if workflow == 'image' else 'audio' if workflow in ('music', 'sfx', 'speech') else 'document' if workflow in ('asr', 'story') else 'video'
    names = {'image': ['image.png'], 'speech': ['audio/preview.wav', 'audio.wav'], 'music': ['bgm.wav'],
             'sfx': ['sfx.wav'], 'asr': ['transcription.srt'], 'story': ['storyboard.json']}.get(workflow, ['video.mp4'])
    if workflow == 'generation':
        if state.get('operation') == 'draft' or job.startswith('gen-'):
            media_type, names = 'document', ['plan.json']
        elif state.get('workflow_kind') == 'character-loop':
            media_type, names = 'image', ['animation.gif', 'animation.webp']
        else:
            media_type, names = 'video', ['video.mp4', 'sample.mp4']
    path = next((p for name in names if (p := _file(folder, name, media_type))), None) if folder else None
    job_status = state.get('status')
    status = job_status if isinstance(job_status, str) and job_status in STATUSES else 'error'
    cover = next((p for name in ('封面-4x3.png', 'cover-landscape.png', 'cover-4x3.png', 'cover.png')
                  if (p := _file(folder, name, 'image'))), None) if folder else None
    if status == 'done' and (not path or workflow == 'story'):
        status = 'preview' if cover else 'draft' if spec or workflow == 'story' else 'error'
    if workflow == 'generation' and status == 'done':
        status = 'draft' if media_type == 'document' else 'preview' if state.get('preview') else 'done'
    stamp = _number(state.get('created')) or _number(state.get('created_at'))
    if not stamp:
        stamp = (folder / 'status.json').stat().st_mtime if folder and (folder / 'status.json').is_file() else folder.stat().st_mtime if folder else 0
    title_sources = (spec, state, prompt, request) if workflow == 'generation' and job.startswith('gen-') else (state, spec, prompt, request)
    title = next((_text(source.get(key), 120) for source in title_sources
                  for key in ('title', 'topic', 'subject', 'prompt', 'text') if _text(source.get(key))), '')
    if not title and workflow == 'speech' and isinstance(spec.get('scenes'), list) and spec['scenes']:
        title = _text(spec['scenes'][0].get('narration'), 100) if isinstance(spec['scenes'][0], dict) else ''
    title = title or LABELS[workflow] + ' · ' + job
    row = _row(_id('project', job), workflow, media_type, title, stamp, status, job, path,
               job_status=job_status, phase=_text(state.get('phase'), 300), error=_text(state.get('error'), 1000),
               engine=_text(state.get('engine') or state.get('image_engine') or state.get('voice_engine')),
               source_url=('/' + workflow + '?project=' + quote(job)) if workflow in ('whiteboard', 'investigation') else
                   {'image': '/image', 'video': '/production', 'speech': '/speech', 'music': '/music', 'sfx': '/music',
                    'story': '/novel', 'motion': '/motion', 'enhance': '/enhance', 'asr': '/subtitles',
                    'generation': '/generation?plan=' + quote(state.get('plan_id') or job)}[workflow],
               quality_review=_text(state.get('quality_review')), plan_id=_text(state.get('plan_id')),
               provenance_url=_url(prompt.get('source_url') or request.get('source_url')),
               collections=['products', 'assets'] if status == 'done' and media_type in ('image', 'video', 'audio') else ['products'],
               temporary=folder is None, thumbnail_url=_output(cover) if cover else _output(path) if path and media_type == 'image' else None,
               deliverables=_deliverables(folder, path, media_type) if folder else [])
    if not path and cover:
        row['preview_url'] = _output(cover)
    if folder:
        hints = [state] + [_read(folder / name, {}) for name in ('video.generation.json', 'bgm.metadata.json',
            'sfx.metadata.json', 'whiteboard.manifest.json', 'investigation.manifest.json', 'video.verification.json', 'verification.json')]
        row.update(_geometry(path, media_type, hints))
        row['sha256'] = _image_hash(path) if path and media_type == 'image' else next(
            (value for hint in hints if isinstance(hint, dict) for key in ('sha256', 'audio_sha256')
             if isinstance(value := hint.get(key), str) and re.fullmatch(r'[a-f0-9]{64}', value)), None)
    return row


def _projects(jobs):
    base = ROOT / 'projects/studio'
    folders = {}
    if base.is_dir() and base.resolve().is_relative_to(ROOT.resolve()):
        for folder in base.iterdir():
            if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}', folder.name) and folder.is_dir() and folder.resolve().parent == base.resolve():
                folders[folder.name] = folder
    live = {key: dict(value) for key, value in list((jobs or {}).items()) if isinstance(key, str) and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}', key) and isinstance(value, dict)}
    for job in sorted(set(folders) | set(live)):
        folder = folders.get(job)
        state = _read(folder / 'status.json') if folder else None
        state = live.get(job, state)
        if isinstance(state, dict):
            yield job, state, folder


def _references():
    store = ROOT / 'assets/image-references'
    if not store.resolve().is_relative_to(ROOT.resolve()):
        return
    for record in store.glob('img-*.json'):
        data = _read(record)
        if not isinstance(data, dict) or not re.fullmatch(r'img-[a-f0-9]{24}', record.stem) or data.get('id') != record.stem:
            continue
        name = data.get('file')
        if not isinstance(name, str) or Path(name).stem != record.stem or Path(name).name != name:
            continue
        path = _file(store, name, 'image')
        if not path or _image_hash(path) != data.get('sha256'):
            continue
        preview = '/api/image-references/preview?id=' + quote(record.stem)
        row = _row(_id('reference', record.stem), 'image-reference', 'image', _text(data.get('name')) or record.stem,
                   _number(data.get('created_at')) or record.stat().st_mtime, 'done', None,
                   preview_url=preview, download_url=preview, absolute_path=str(path), size_bytes=path.stat().st_size,
                   source_tool='image-references', source_url='/image', provenance_url=_url(data.get('source_url')), collections=['assets'],
                   thumbnail_url=preview, reference_id=record.stem, sha256=data.get('sha256'),
                   deliverables=[{'label': '参考图', 'url': preview, 'kind': 'image'}])
        row.update(_geometry(path, 'image', [data]))
        yield row


def _media(job, folder):
    records = _read(folder / 'media.json', [])
    if not job.startswith('investigation-') or not isinstance(records, list) or len(records) > 200:
        return
    seen = set()
    for data in records:
        if not isinstance(data, dict):
            continue
        identity, kind = data.get('id'), data.get('kind')
        if not isinstance(identity, str) or not re.fullmatch(r'media-[a-f0-9]{20}(?:-evidence)?', identity) or identity in seen:
            continue
        seen.add(identity)
        media_type = 'image' if kind == 'evidence' else kind
        relative = data.get('path')
        if media_type not in ('image', 'video', 'audio') or not isinstance(relative, str) or not relative.startswith('assets/media/'):
            continue
        path = _file(folder / 'assets/media', relative.removeprefix('assets/media/'), media_type)
        if not path:
            continue
        row = _row(_id('media', job + ':' + identity), 'registered-media', media_type,
                   _text(data.get('description')) or _text(data.get('name')) or identity,
                   _number(data.get('registered_at')) or path.stat().st_mtime, 'done', job, path,
                   source_tool='investigation', source_url='/investigation?project=' + quote(job), provenance_url=_url(data.get('source_url')),
                   collections=['assets'], media_id=identity, asset_kind=kind,
                   sha256=data.get('sha256') if isinstance(data.get('sha256'), str) and re.fullmatch(r'[a-f0-9]{64}', data['sha256']) else None,
                   thumbnail_url=_output(path) if media_type == 'image' else None,
                   deliverables=[{'label': '已登记素材', 'url': _output(path), 'kind': media_type}])
        row.update(_geometry(path, media_type, [data]))
        yield row


def _drafts():
    folder = ROOT / 'projects/drafts'
    for record in folder.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{12}', record.stem):
            continue
        path = _file(folder, record.name, 'document')
        data = _read(record)
        if not path or not isinstance(data, dict) or not isinstance(data.get('scenes'), list):
            continue
        identity = _id('draft', record.stem)
        url = '/api/library/file?id=' + identity
        yield _row(identity, 'story', 'document', _text(data.get('title')) or '小说分镜 · ' + record.stem,
                   record.stat().st_mtime, 'draft', 'draft-' + record.stem, path,
                   source_tool='novel', source_url='/novel?draft=' + identity, draft_id=record.stem, collections=['products'],
                   preview_url=url, download_url=url, deliverables=[{'label': '完整分镜', 'url': url, 'kind': 'storyboard'}])


def _metadata():
    path = ROOT / 'config/library-metadata.json'
    if not path.parent.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('作品元数据目录越界')
    if not path.exists():
        return {'version': 1, 'items': {}}
    value = _read(path)
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('items'), dict):
        raise ValueError('作品元数据文件损坏，已保留原文件，请先检查 config/library-metadata.json')
    for identity, entry in value['items'].items():
        if (not re.fullmatch(r'lib-[a-f0-9]{24}', identity) or not isinstance(entry, dict)
                or set(entry) - {'title', 'favorite', 'tags', 'updated_at'}
                or ('title' in entry and (not isinstance(entry['title'], str) or not 1 <= len(entry['title']) <= 200 or _text(entry['title']) != entry['title']))
                or ('favorite' in entry and not isinstance(entry['favorite'], bool))
                or ('tags' in entry and (not isinstance(entry['tags'], list) or len(entry['tags']) > 16
                    or any(not isinstance(tag, str) or not 1 <= len(tag) <= 32 or _text(tag) != tag for tag in entry['tags'])))):
            raise ValueError('作品元数据记录损坏，已保留原文件')
    return value


def _all(jobs=None):
    rows = [*list(_references()), *list(_drafts())]
    for job, state, folder in _projects(jobs):
        product = _product(job, state, folder)
        if product:
            rows.append(product)
        if folder:
            rows.extend(_media(job, folder))
    metadata = _metadata()['items']
    references = {row.get('sha256'): row['reference_id'] for row in rows if row.get('reference_id')}
    for row in rows:
        if row['media_type'] == 'image' and row.get('sha256') in references:
            row['reference_id'] = references[row['sha256']]
        changes = metadata.get(row['id'], {})
        if isinstance(changes, dict):
            row.update({key: changes[key] for key in ('title', 'favorite', 'tags') if key in changes})
    return sorted(rows, key=lambda row: (-row['created_at'], row['id']))


def catalog(view='products', q='', kind='all', status=None, favorite=None, jobs=None):
    if view not in ('products', 'assets'):
        raise ValueError('目录视图应为 products 或 assets')
    status = status or 'done'
    if not isinstance(kind, str) or not isinstance(status, str) or kind not in WORKFLOWS | MEDIA_TYPES | {'all', 'image-reference', 'registered-media', 'evidence'} or status not in STATUSES | {'all'}:
        raise ValueError('未知的作品类型或状态筛选')
    if not isinstance(q, str) or len(q) > 200 or favorite not in (None, '0', '1'):
        raise ValueError('搜索词最多 200 字，收藏筛选应为 0 或 1')
    rows = [row for row in _all(jobs) if view in row['collections']]
    if view == 'assets':
        grouped = {}
        for row in sorted(rows, key=lambda item: ('products' not in item['collections'], -item['created_at'])):
            sha = row.get('sha256')
            key = (row['media_type'], sha) if isinstance(sha, str) and re.fullmatch(r'[a-f0-9]{64}', sha) else row['id']
            if key not in grouped:
                grouped[key] = row
            else:
                original = grouped[key]
                if row.get('reference_id'):
                    original['reference_id'] = row['reference_id']
                original.setdefault('registered_copies', []).append({'id': row['id'], 'project_id': row['project_id'],
                                                                    'media_id': row.get('media_id')})
        rows = sorted(grouped.values(), key=lambda row: (-row['created_at'], row['id']))
    counts = {key: dict(Counter(row[key] for row in rows)) for key in ('status', 'workflow', 'media_type')}
    words = q.casefold().split()
    rows = [row for row in rows if (status == 'all' or row['status'] == status)
            and (kind == 'all' or kind in (row['workflow'], row['media_type'], row.get('asset_kind'))
                 or kind == 'image-reference' and row.get('reference_id')
                 or kind == 'registered-media' and any(copy.get('media_id') for copy in row.get('registered_copies', [])))
            and (favorite is None or row['favorite'] == (favorite == '1'))
            and all(word in ' '.join([row['title'], row['project_id'] or '', row['workflow'], *row['tags']]).casefold() for word in words)]
    return {'items': rows, 'total': len(rows), 'view': view, 'counts': counts,
            'filters': {'q': q, 'kind': kind, 'status': status, 'favorite': favorite},
            'scope': '工作台项目主交付物与已登记素材；不包含模型、缓存、项目中间帧或音色参考录音'}


def save_metadata(data, jobs=None):
    if not isinstance(data, dict) or set(data) - {'id', 'title', 'favorite', 'tags'} or len(data) < 2:
        raise ValueError('仅接受作品 ID 与 title/favorite/tags 元数据')
    identity = data.get('id')
    if not isinstance(identity, str) or not re.fullmatch(r'lib-[a-f0-9]{24}', identity):
        raise ValueError('无效的作品 ID')
    changes = {}
    if 'title' in data:
        if not isinstance(data['title'], str) or not 1 <= len(data['title'].strip()) <= 200 or _text(data['title']) != data['title'].strip():
            raise ValueError('标题应为 1–200 字且不含控制字符')
        changes['title'] = data['title'].strip()
    if 'favorite' in data:
        if not isinstance(data['favorite'], bool):
            raise ValueError('收藏值必须为布尔值')
        changes['favorite'] = data['favorite']
    if 'tags' in data:
        tags = data['tags']
        if not isinstance(tags, list) or len(tags) > 16 or any(not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 32 or _text(tag) != tag.strip() for tag in tags):
            raise ValueError('最多 16 个标签，每个 1–32 字且不含控制字符')
        changes['tags'] = list(dict.fromkeys(tag.strip() for tag in tags))
    with LOCK:
        if not any(row['id'] == identity for row in _all(jobs)):
            raise ValueError('作品或素材不存在，不能保存任意 ID')
        folder = ROOT / 'config'
        folder.mkdir(parents=True, exist_ok=True)
        with FileLock(str(folder / 'library-metadata.lock'), timeout=5):
            document = _metadata()
            document['items'].setdefault(identity, {}).update(changes, updated_at=time.time())
            temporary = folder / ('library-metadata.' + uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
                os.replace(temporary, folder / 'library-metadata.json')
            finally:
                temporary.unlink(missing_ok=True)
    return {'item': next(row for row in _all(jobs) if row['id'] == identity)}


def get(handler, route, jobs=None):
    if route.path not in ('/api/library', '/api/library/item', '/api/library/file'):
        return False
    try:
        query = parse_qs(route.query, keep_blank_values=True)
        if route.path in ('/api/library/item', '/api/library/file'):
            if set(query) != {'id'} or len(query['id']) != 1 or not re.fullmatch(r'lib-[a-f0-9]{24}', query['id'][0]):
                raise ValueError('请提供目录中已存在的作品 ID')
            item = next((row for row in _all(jobs) if row['id'] == query['id'][0]), None)
            if not item:
                raise ValueError('作品或素材不存在')
            if route.path.endswith('/item'):
                handler.reply({'item': item})
            elif item['absolute_path']:
                handler.send_file(Path(item['absolute_path']))
            else:
                raise ValueError('该工程尚无可下载的主要文件')
            return True
        if set(query) - {'view', 'q', 'kind', 'status', 'favorite'} or any(len(value) != 1 for value in query.values()):
            raise ValueError('目录筛选包含未知或重复参数')
        handler.reply(catalog(**{key: value[0] for key, value in query.items()}, jobs=jobs))
    except (ValueError, OSError) as error:
        handler.reply({'error': str(error)}, 400)
    return True


def post(handler, data, jobs=None):
    if handler.path != '/api/library/metadata':
        return False
    handler.reply(save_metadata(data, jobs))
    return True

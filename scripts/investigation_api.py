"""Persistent investigation projects, local media registry and frozen render jobs."""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote

import creation_settings as settings
import investigation_draft as drafting
import voice_library

ROOT = settings.ROOT
LOCK = threading.RLock()
ACTIVE = set()
MEDIA_SUFFIXES = {'video': {'.mp4', '.mov', '.mkv', '.webm', '.m4v'},
                  'image': {'.png', '.jpg', '.jpeg', '.webp'},
                  'evidence': {'.png', '.jpg', '.jpeg', '.webp'},
                  'audio': {'.wav', '.mp3', '.m4a', '.flac'}}


def project_path(job):
    if not isinstance(job, str) or not re.fullmatch(r'investigation-[a-f0-9]{10}', job):
        raise ValueError('无效的调查项目 ID')
    root = (ROOT/'projects/studio').resolve()
    dest = (root/job).resolve()
    if not dest.is_relative_to(root) or not dest.is_dir():
        raise ValueError('调查项目不存在')
    return dest


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else copy.deepcopy(default)


def hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def output_url(dest, path):
    path = Path(path).resolve()
    if not path.is_relative_to(dest.resolve()) or not path.is_file():
        raise ValueError('输出文件不存在或越界')
    return '/outputs/' + dest.name + '/' + quote(path.relative_to(dest).as_posix(), safe='/')


def media_catalog(dest, verify=False):
    rows = read_json(dest/'media.json', [])
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError('项目素材台账无效')
    seen = set()
    for row in rows:
        identity = drafting.ident(row.get('id'), '素材 ID')
        if identity in seen or row.get('kind') not in MEDIA_SUFFIXES:
            raise ValueError('素材台账包含无效或重复记录')
        seen.add(identity)
        relative = row.get('path')
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError('素材路径必须位于项目内')
        path = (dest/relative).resolve()
        if (not path.is_relative_to((dest/'assets/media').resolve()) or not path.is_file()
                or path.suffix.lower() not in MEDIA_SUFFIXES[row['kind']]):
            raise ValueError('已登记素材缺失或越界：' + identity)
        if verify and hash_file(path) != row.get('sha256'):
            raise ValueError('素材已在登记后被修改，请重新导入：' + identity)
        row['preview_url'] = output_url(dest, path)
    return rows


def _probe(path):
    # Fixed code, filename exclusively in argv; no shell and no GPU imports.
    python = ROOT/'tools/.venv/Scripts/python.exe'
    code = ('import av,json,sys; c=av.open(sys.argv[1]); '
            'v=next((s for s in c.streams if s.type=="video"),None); '
            'a=next((s for s in c.streams if s.type=="audio"),None); '
            'd=float(c.duration/av.time_base) if c.duration else '
            '(float(v.duration*v.time_base) if v is not None and v.duration else 0); '
            'print(json.dumps({"duration":d,"width":v.width if v else 0,"height":v.height if v else 0,'
            '"has_video":v is not None,"has_audio":a is not None})); c.close()')
    process = subprocess.run([str(python), '-c', code, str(path)], capture_output=True, text=True,
                             encoding='utf-8', timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        raise ValueError('素材不能被解码，请确认它是有效的图片、视频或音频')
    return json.loads(process.stdout)


def register_media(dest, data):
    if set(data) - {'job_id', 'path', 'kind', 'source_id', 'source_url', 'description'}:
        raise ValueError('素材登记包含未知字段')
    kind = data.get('kind')
    if kind not in MEDIA_SUFFIXES:
        raise ValueError('素材类型应为 video/image/evidence/audio')
    raw = drafting.text(data.get('path'), '本地素材路径', 2000, 1)
    path = Path(raw)
    if not path.is_absolute() or raw.startswith(('\\\\', '//')):
        raise ValueError('请填写本机磁盘上的完整素材路径，不支持网络共享')
    path = path.resolve()
    if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES[kind] or not 0 < path.stat().st_size <= 2 * 1024**3:
        raise ValueError('素材文件不存在、格式不符或超过 2 GB')
    spec = read_json(dest/'storyboard.json', {})
    source_id = data.get('source_id') or ''
    if source_id and source_id not in {row['id'] for row in spec.get('sources', [])}:
        raise ValueError('素材关联来源不存在，请先保存来源台账')
    info = _probe(path)
    if kind in ('video', 'image', 'evidence') and not info['has_video']:
        raise ValueError('视觉素材需要可解码的图像流')
    if kind == 'video' and info['duration'] <= 0:
        raise ValueError('视频没有有效时长')
    if kind == 'audio' and not info['has_audio']:
        raise ValueError('配乐素材没有音轨')
    digest = hash_file(path)
    identity = 'media-' + digest[:20] + ('-evidence' if kind == 'evidence' else '')
    rows = media_catalog(dest)
    existing = next((row for row in rows if row['id'] == identity), None)
    if existing:
        return existing, rows
    target = dest/'assets/media'/(identity + path.suffix.lower())
    target.parent.mkdir(parents=True, exist_ok=True)
    if path != target.resolve():
        temporary = target.with_suffix(target.suffix + '.tmp')
        shutil.copyfile(path, temporary)
        os.replace(temporary, target)
    row = {'id': identity, 'kind': kind, 'path': target.relative_to(dest).as_posix(), 'sha256': digest,
           'name': path.name, 'duration': info['duration'], 'width': info['width'], 'height': info['height'],
           'source_id': source_id, 'source_url': drafting.public_url(data['source_url']) if data.get('source_url') else '',
           'description': drafting.text(data.get('description', ''), '素材说明', 1000), 'registered_at': time.time()}
    rows.append(row)
    drafting.write_json(dest/'media.json', [{key: value for key, value in item.items() if key != 'preview_url'} for item in rows])
    return row, media_catalog(dest)


def snapshot(data, dest, render=False):
    if not isinstance(data, dict) or set(data) - {'job_id', 'storyboard', 'voice_preset_id', 'voice', 'characters'}:
        raise ValueError('长片请求包含未知字段')
    original = data.get('storyboard')
    spec = drafting.storyboard(original)
    config = settings.load()
    identity = data.get('voice_preset_id', original.get('voice_preset_id'))
    characters = data.get('characters', original.get('character_preset_ids', {}))
    voice = data.get('voice', {})
    if not isinstance(voice, dict) or set(voice) - {'speed', 'emotion', 'intensity'}:
        raise ValueError('全片配音只接受语速、情感与强度覆盖；参考音频请选择预设')
    if not isinstance(characters, dict) or len(characters) > 16:
        raise ValueError('角色音色最多 16 个')
    catalog = voice_library.catalog()
    if identity:
        preset = voice_library.resolve(identity, catalog)
        config['voice'] = preset['voice']
        spec['voice_preset_id'] = preset['id']
    config['voice'] = voice_library.validate_voice(settings.merge(config['voice'], voice), catalog['references'])
    spec['characters'], spec['character_preset_ids'] = {}, {}
    for raw_name, preset_id in characters.items():
        name = voice_library.role_name(raw_name)
        if name in spec['characters']:
            raise ValueError('角色名称重复')
        preset = voice_library.resolve(preset_id, catalog)
        spec['characters'][name] = preset['voice']
        spec['character_preset_ids'][name] = preset['id']
    for scene in spec['scenes']:
        speaker = scene['speaker']
        if speaker != '旁白' and speaker not in spec['characters']:
            raise ValueError('角色尚未分配音色：' + speaker)
        if scene.get('voice_preset_id'):
            scene['voice'] = voice_library.resolve(scene['voice_preset_id'], catalog)['voice']
    config['output'].update(width=1920, height=1080, fps=30)
    spec.update(settings=config, backends={'tts': 'local', 'asr': 'local'}, media=media_catalog(dest, verify=render))
    return spec


def coverage(spec):
    media = {row['id']: row for row in spec.get('media', [])}
    sources = {row['id']: row for row in spec['sources']}
    gaps = []
    def add(scene, message, severity='error'):
        gaps.append({'scene_id': scene['id'] if scene else None, 'message': message, 'severity': severity})
    for scene in spec['scenes']:
        row = media.get(scene['media_id'])
        kind = scene['kind']
        if scene['media_id'] and not row:
            add(scene, '关联素材未登记在当前项目中')
        elif kind in ('video', 'image') and not row:
            add(scene, '需要补充与旁白匹配的' + ('真实视频区间' if kind == 'video' else '图片'))
        elif row and (kind == 'video' and row['kind'] != 'video' or kind in ('image', 'evidence') and row['kind'] not in ('image', 'evidence')):
            add(scene, '素材类型与镜头视觉类型不匹配')
        if kind == 'evidence' and not row:
            excerpt = ''.join(scene['text'].split())
            if not excerpt or not any(excerpt in ''.join(sources[source]['content'].split()) for source in scene['source_ids']):
                add(scene, '证据镜头需要原件图片，或绑定来源并逐字摘录原文')
        if kind == 'diagram' and not scene['points'] and not scene['text']:
            add(scene, '机制图需要要点或解释文字')
        if kind == 'video' and row and scene['media_start'] >= row['duration']:
            add(scene, '素材起点已超出原视频时长')
        if scene['fact_status'] != 'analysis' and not scene['source_ids']:
            add(scene, '外部事实需要绑定来源 ID')
        if scene['fact_status'] == 'needs_review':
            add(scene, '来源和旁白仍待复核，AI 写稿不等于核查', 'warning')
    if spec['mode'] == 'investigation' and spec['scenes'][0]['kind'] != 'video':
        add(spec['scenes'][0], '调查开场需要与事件相关的真实动作；方法教学请使用机制讲解模式')
    total = sum(len(row['narration']) for row in spec['scenes'])
    share = sum(len(row['narration']) for row in spec['scenes'] if row['kind'] == 'video') / max(1, total)
    if spec['mode'] == 'investigation' and share < .5:
        add(None, f'按文字粗估真实动态约 {share:.0%}，建议继续补充相关素材；最终按实际音轨复核', 'warning')
    bgm = spec.get('bgm', {})
    if bgm.get('mode') == 'media' and media.get(bgm.get('media_id'), {}).get('kind') != 'audio':
        add(None, '配乐需选择本项目已登记的音频素材')
    return gaps


def deliverables(dest):
    rows = [('manuscript.md', '完整口播稿'), ('sources.json', '来源台账'), ('coverage.json', '素材覆盖与缺口'),
            ('storyboard.json', '完整分镜'), ('investigation.manifest.json', '渲染清单'),
            ('script.md', '带来源的口播稿'), ('sources.csv', '来源表格'), ('chapters.txt', '章节时间码'),
            ('verification.json', '成片检查记录'), ('publish-copy.md', '八平台发布文案'), ('delivery.zip', '完整交付包'),
            ('production-report.md', '制作与检查说明'), ('publish.md', '发布文案')]
    return [{'url': output_url(dest, dest/path), 'label': label} for path, label in rows if (dest/path).is_file()]


def save_storyboard(dest, spec):
    previous = dest/'storyboard.json'
    if previous.exists():
        history = dest/'history'
        history.mkdir(exist_ok=True)
        shutil.copyfile(previous, history/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json'))
    drafting.write_json(previous, spec)
    drafting.write_json(dest/'sources.json', {'review_note': drafting.REVIEW_NOTE, 'sources': spec['sources']})
    gaps = coverage(spec)
    drafting.write_json(dest/'coverage.json', gaps)
    lines = ['# ' + spec['title'], '', drafting.REVIEW_NOTE, '']
    for chapter in spec['chapters']:
        lines.extend(['## ' + chapter['title'], ''])
        for scene in spec['scenes']:
            if scene['chapter_id'] == chapter['id']:
                lines.extend([f'[{scene["id"]}] {scene["speaker"]}（{scene["fact_status"]}；来源：{", ".join(scene["source_ids"]) or "方法解释"}）', '', scene['narration'], ''])
    (dest/'manuscript.md').write_text('\n'.join(lines), encoding='utf-8')
    return gaps


def project_data(dest):
    spec = read_json(dest/'storyboard.json')
    media = media_catalog(dest)
    if spec:
        spec['media'] = media
    return {'job_id': dest.name, 'storyboard': spec, 'media': media, 'status': read_json(dest/'status.json', {}),
            'gaps': coverage(spec) if spec else [], 'downloads': deliverables(dest)}


def _artifacts(dest, render):
    manifest = read_json(dest/'investigation.manifest.json')
    if not isinstance(manifest, dict):
        raise ValueError('渲染器未生成 investigation.manifest.json')
    def link(relative):
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError('渲染输出路径无效')
        return output_url(dest, dest/relative)
    result = {'previews': [link(path) for path in manifest.get('preview_frames', [])],
              'covers': [link(path) for path in manifest.get('covers', [])],
              'manifest_url': link('investigation.manifest.json'), 'storyboard_url': link('storyboard.json'),
              'downloads': deliverables(dest)}
    for key in ('duration_seconds', 'estimated_duration', 'duration_note', 'target_reached', 'target_difference_seconds', 'target_seconds'):
        if key in manifest:
            result[key] = manifest[key]
    if render:
        result.update(video=link(manifest.get('video', 'video.mp4')), subtitle=link(manifest.get('subtitle', 'subtitles.srt')))
        for key, alias in [('script', 'manuscript'), ('sources', 'source_ledger'), ('publishing', 'publish_copy'),
                           ('bundle', 'bundle'), ('verification', 'verification')]:
            if manifest.get(key):
                result[alias] = link(manifest[key])
    elif not result['previews']:
        raise ValueError('预览没有生成图片')
    return result


def _save_status(dest, state):
    drafting.write_json(dest/'status.json', state)


def run_job(jobs, job, operation):
    dest = project_path(job)
    state = jobs[job]
    def update(**changes):
        state.update(changes, updated=time.time())
        _save_status(dest, state)
    try:
        update(status='running', phase='正在恢复章节' if operation == 'draft' else '准备长片处理')
        if operation == 'draft':
            spec = drafting.draft(read_json(dest/'request.json'), dest, update)
            spec['media'] = media_catalog(dest)
            gaps = save_storyboard(dest, spec)
            update(status='done', phase='长稿已生成，等待审阅与补充素材', progress=100, storyboard=spec,
                   gaps=gaps, storyboard_url=output_url(dest, dest/'storyboard.json'), downloads=deliverables(dest))
            return
        from studio_extensions import launch, PYTHON
        command = [PYTHON, ROOT/'scripts/investigation_pipeline.py', dest]
        if operation == 'preview':
            command.append('--preview')
        process = launch(job, command)
        while process.poll() is None:
            try:
                pipeline = read_json(dest/'state.json', {})
                changes = {key: pipeline[key] for key in ('phase', 'progress') if key in pipeline}
                if not changes.get('phase') and pipeline.get('running'):
                    changes['phase'] = '正在处理：' + str(pipeline['running'])
                if changes and any(state.get(key) != value for key, value in changes.items()):
                    update(**changes)
            except (OSError, ValueError):
                pass
            time.sleep(1)
        if process.returncode:
            pipeline = read_json(dest/'state.json', {})
            raise RuntimeError(pipeline.get('error') or f'长片处理失败（退出码 {process.returncode}），日志 logs/{job}.log')
        update(status='done', progress=100, phase='视频已完成，请试听审片' if operation == 'render' else '预览已完成',
               **_artifacts(dest, operation == 'render'))
    except Exception as exc:
        update(status='error', phase='任务中断，可修复后继续', error=str(exc), resumable=True)
    finally:
        with LOCK:
            ACTIVE.discard(job)


def _enqueue(jobs, dest, operation):
    job = dest.name
    if job in ACTIVE:
        raise ValueError('该项目正在处理，请等待完成后编辑')
    if len(ACTIVE) >= 2:
        raise ValueError('已有两个调查任务运行，请稍后再提交')
    state = {'kind': 'investigation', 'operation': operation, 'status': 'queued', 'created': time.time(),
             'phase': '任务已提交', 'progress': 0, 'resumable': True,
             'title': read_json(dest/'storyboard.json', {}).get('title', read_json(dest/'request.json', {}).get('topic', '调查长片'))[:100]}
    jobs[job] = state
    _save_status(dest, state)
    ACTIVE.add(job)
    threading.Thread(target=run_job, args=(jobs, job, operation), daemon=True).start()


def _new_project():
    job = 'investigation-' + uuid.uuid4().hex[:10]
    dest = ROOT/'projects/studio'/job
    dest.mkdir(parents=True)
    return dest


def health():
    checks = []
    for label, path in [('长片编排', ROOT/'scripts/investigation_pipeline.py'), ('Node.js', ROOT/'tools/node/node.exe'),
                        ('FFmpeg', ROOT/'tools/ffmpeg.exe'), ('本地配音', ROOT/'apps/index-tts/checkpoints/config.yaml'),
                        ('字幕对齐', ROOT/'models/Qwen3-ForcedAligner-0.6B/config.json')]:
        checks.append({'name': label, 'ready': path.is_file(), 'message': '可用' if path.is_file() else '尚未就绪'})
    checks.append({'name': '本地编剧配置', 'ready': bool(settings.load()['story']['local_model']),
                   'message': settings.load()['story']['local_model'] or '请先在设置中选择本地编剧模型'})
    return {'ready': all(row['ready'] for row in checks), 'checks': checks, 'narrative_modes': drafting.MODES,
            'review_note': drafting.REVIEW_NOTE, 'limits': {'target_minutes': 12, 'scenes': 96, 'sources': 24}}


def get(handler, route):
    if not route.path.startswith('/api/investigation/'):
        return False
    try:
        query = parse_qs(route.query)
        if route.path.endswith('/health'):
            handler.reply(health())
        elif route.path.endswith('/example'):
            handler.reply(drafting.example())
        elif route.path.endswith('/topics'):
            handler.reply(drafting.hot_topics())
        elif route.path.endswith('/project'):
            handler.reply(project_data(project_path(query.get('job_id', [''])[0])))
        else:
            handler.reply({'error': '调查接口不存在'}, 404)
    except (ValueError, OSError, TypeError) as exc:
        handler.reply({'error': str(exc)}, 400)
    return True


def post(handler, data, jobs):
    prefix = '/api/investigation/'
    if not handler.path.startswith(prefix):
        return False
    operation = handler.path[len(prefix):]
    if not isinstance(data, dict):
        raise ValueError('请求必须是 JSON 对象')
    if operation == 'source':
        if set(data) != {'url'}:
            raise ValueError('正文抓取仅接受 url')
        handler.reply({'source': drafting.source_from_url(data['url'])})
        return True
    if operation not in ('draft', 'save', 'preview', 'render', 'resume', 'media'):
        handler.reply({'error': '调查接口不存在'}, 404)
        return True
    with LOCK:
        if operation == 'draft':
            if set(data) - {'topic', 'mode', 'narrative_mode', 'target_minutes', 'hot_relevance', 'sources'}:
                raise ValueError('写稿请求包含未知字段')
            payload = drafting.request(data)
            if not any(len(row['content']) >= 100 for row in payload['sources']):
                raise ValueError('请先读取或填写至少一条含 100 字正文的来源')
            if len(ACTIVE) >= 2:
                raise ValueError('已有两个调查任务运行，请稍后再提交')
            dest = _new_project()
            drafting.write_json(dest/'request.json', payload)
            _enqueue(jobs, dest, 'draft')
        else:
            dest = project_path(data['job_id']) if data.get('job_id') else None
            if dest and dest.name in ACTIVE:
                raise ValueError('项目正在处理，暂不能编辑、导入或重复提交')
            if operation == 'resume':
                if set(data) != {'job_id'} or dest is None:
                    raise ValueError('恢复任务仅接受 job_id')
                state = read_json(dest/'status.json', {})
                previous = state.get('operation')
                if previous not in ('draft', 'preview', 'render') or state.get('status') == 'done':
                    raise ValueError('此任务没有待恢复的操作')
                # Frozen storyboard is deliberately not re-resolved from live presets.
                if previous != 'draft':
                    media_catalog(dest, verify=True)
                _enqueue(jobs, dest, previous)
            elif operation == 'media':
                if dest is None:
                    raise ValueError('请先保存项目，再登记本地素材')
                row, media = register_media(dest, data)
                handler.reply({'item': row, 'media': media})
                return True
            else:
                if dest is None:
                    # Validate text before creating an empty project; no external effects.
                    drafting.storyboard(data.get('storyboard'))
                    dest = _new_project()
                spec = snapshot(data, dest, render=operation == 'render')
                gaps = save_storyboard(dest, spec)
                if operation == 'save':
                    state = {'kind': 'investigation', 'operation': 'save', 'status': 'done', 'created': time.time(),
                             'title': spec['title'], 'phase': '分镜已保存', 'gaps': gaps}
                    jobs[dest.name] = state
                    _save_status(dest, state)
                    handler.reply({'job_id': dest.name, 'storyboard': spec, 'gaps': gaps, 'downloads': deliverables(dest)})
                    return True
                blocking = [row for row in gaps if row['severity'] == 'error']
                if blocking:
                    state = {'kind': 'investigation', 'operation': 'save', 'status': 'done', 'created': time.time(),
                             'title': spec['title'], 'phase': '分镜已保存，素材与来源覆盖尚未补齐', 'gaps': gaps,
                             'downloads': deliverables(dest)}
                    jobs[dest.name] = state
                    _save_status(dest, state)
                    handler.reply({'error': '素材或来源覆盖不足，请先补齐以下缺口', 'job_id': dest.name, 'gaps': gaps}, 422)
                    return True
                _enqueue(jobs, dest, operation)
        handler.reply({'job_id': dest.name}, 202)
    return True

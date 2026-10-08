"""Generation workshop routes; slow work always runs in an isolated process."""
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
import re
from urllib.parse import parse_qs, quote
import uuid

from prompt_library import ROOT
import generation_plans as plans
import generation_workers as workers
import studio_edition

QUEUE_LOCK = threading.Lock()
KINDS = {'code-animation', 'character-loop', 'blender-previs'}


def write(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def runtime():
    import generation_automation
    node = ROOT/'tools/node/node.exe'
    playwright = ROOT/'apps/simon-skills/skills/whiteboard-video/node_modules/playwright/package.json'
    browser = list((ROOT/'cache/ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))
    code_ready = node.is_file() and playwright.is_file() and bool(browser) and (ROOT/'tools/ffmpeg.exe').is_file()
    if studio_edition.is_friend():
        return {'code_animation': {'ready': code_ready, 'message': 'CPU 逐帧渲染' if code_ready else '请运行 Install-Renderers.ps1 安装渲染组件'},
                'writing': generation_automation.writer_status()}
    blender = workers.blender_path()
    return {'code_animation': {'ready': code_ready, 'message': 'CPU 逐帧渲染' if code_ready else '请运行 Install-Renderers.ps1 安装渲染组件'},
            'character_loop': {'ready': True, 'message': '关键姿势组帧与透明动图'},
            'blender': {'ready': bool(blender), 'path': str(blender) if blender else None,
                        'message': '几何白模预演，可编辑 .blend' if blender else '需要安装官方 Blender'},
            'writing': generation_automation.writer_status()}


def get(handler, route, jobs=None):
    if not route.path.startswith('/api/generation/'):
        return False
    if studio_edition.reject(handler, route.geturl(), 'GET'):return True
    try:
        query = parse_qs(route.query, keep_blank_values=True)
        if any(len(v) != 1 for v in query.values()):
            raise ValueError('查询参数不能重复')
        if route.path == '/api/generation/catalog':
            handler.reply({**plans.catalog(), 'runtime': runtime()})
        elif route.path in ('/api/generation/plan', '/api/generation/handoff'):
            plan = plans.load(query.get('id', [''])[0])
            handler.reply(plan if route.path.endswith('/plan') else {'text': plans.handoff(plan)})
        elif route.path == '/api/generation/example':
            if query.get('kind', ['code-animation'])[0] != 'code-animation':
                raise ValueError('当前示例为代码动画')
            handler.reply({'html': (ROOT/'examples/code-animation.html').read_text(encoding='utf-8')})
        else:
            handler.reply({'error': '没有此生成接口'}, 404)
    except (ValueError, OSError) as exc:
        handler.reply({'error': str(exc)}, 400)
    return True


def _outputs(dest, result):
    mapped = {}
    for key in ('video', 'image', 'gif', 'webp', 'qa', 'blend', 'subtitle', 'storyboard_url'):
        relative = result.get(key)
        if relative is None:
            continue
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError('渲染器返回了无效的交付路径')
        path = (dest/relative).resolve()
        if not path.is_relative_to(dest.resolve()) or not path.is_file() or not path.stat().st_size:
            raise ValueError('渲染器未生成有效交付文件：' + relative)
        mapped[key] = '/outputs/' + dest.name + '/' + quote(relative, safe='/')
    return mapped


def _attach_generated(state, dest, result):
    """Attach real per-shot media, never approve it or overwrite a newer edit."""
    plan = plans.load(state['plan_id'])
    if plan['revision'] != state['plan_revision']:
        return {'plan_attached': False, 'plan_update_note': '生成期间计划已修改，产物保留在作品库，未覆盖新分镜'}
    rows = result.get('shot_outputs', [])
    if not rows and len(plan['shots']) == 1:
        relative = result.get('video') or result.get('gif')
        if relative:
            rows = [{'id': plan['shots'][0]['id'], 'path': relative}]
    if not isinstance(rows, list) or len(rows) > len(plan['shots']):
        raise ValueError('渲染器镜头清单无效')
    changes = {}
    shot_ids = {shot['id'] for shot in plan['shots']}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise ValueError('渲染器镜头记录无效')
        if not isinstance(row.get('id'), str) or row['id'] not in shot_ids or row['id'] in changes:
            raise ValueError('渲染器镜头 ID 不属于当前计划或重复')
        path = (dest/row['path']).resolve()
        if not path.is_relative_to(dest.resolve()) or not path.is_file() or path.suffix.lower() not in plans.MEDIA_SUFFIXES:
            raise ValueError('渲染器镜头素材缺失或越界')
        changes[row.get('id')] = str(path)
    if not changes:
        return {'plan_attached': False}
    for shot in plan['shots']:
        if shot['id'] in changes:
            shot.update(asset_path=changes[shot['id']], status='generated')
    try:
        updated = plans.save(plan)
        return {'plan_attached': True, 'plan_revision': updated['revision']}
    except plans.RevisionConflict:
        return {'plan_attached': False, 'plan_update_note': '计划已更新，未自动关联到新版分镜'}


def _run(jobs, job, dest, operation, kind):
    state = jobs[job]
    def update(**changes):
        state.update(changes); write(dest/'status.json', state)
    try:
        if studio_edition.is_friend() and (not studio_edition.generation_allowed(kind)
                or operation != 'draft' and kind != 'code-animation'):
            raise ValueError('朋友版不支持此生成任务；原素材已保留。')
        phase = '正在生成可编辑分镜' if operation == 'draft' else {
            'code-animation': '正在配音、设计画面与逐帧渲染' if operation == 'compose' else '正在逐帧渲染动画',
            'character-story': '正在生成镜头画面、配音与字幕',
            'character-loop': '正在生成角色关键姿势与循环动画',
            'blender-previs': '正在渲染几何白模与相机预演',
        }.get(kind, '正在渲染')
        update(status='running', phase=phase)
        script = 'generation_automation.py' if operation in ('draft', 'compose') else 'generation_workers.py'
        argument = operation if script == 'generation_automation.py' else kind
        command = [str(ROOT/'tools/.venv/Scripts/python.exe'), str(ROOT/'scripts'/script), argument, str(dest)]
        env = os.environ.copy(); env.update(PYTHONUTF8='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HOME=str(ROOT/'cache/huggingface'))
        with (dest/'worker.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                code = process.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)
                else:
                    process.kill()
                raise RuntimeError('生成超过一小时，任务已停止，已有素材保留')
        if code:
            error_path = dest/'failure.json'
            detail = json.loads(error_path.read_text(encoding='utf-8')).get('error') if error_path.is_file() else ''
            raise RuntimeError(detail or '生成失败，请查看工程 worker.log；已有素材已保留')
        result = json.loads((dest/'render-result.json').read_text(encoding='utf-8'))
        if not isinstance(result, dict):
            raise ValueError('渲染器返回格式错误')
        metadata = {}
        for key in ('width', 'height', 'fps', 'frames', 'duration', 'plan_revision'):
            if key in result:
                value = result[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError('渲染器返回无效元数据：'+key)
                metadata[key] = value
        if operation == 'draft':
            saved = plans.load(state['plan_id'])
            if result.get('plan_revision') != saved['revision'] or saved['revision'] <= state['plan_revision']:
                raise ValueError('编剧没有保存新的创作方案，未记为完成')
        links = _outputs(dest, result)
        if operation != 'draft' and not (links.get('video') or links.get('gif')):
            raise RuntimeError('渲染器没有生成视频或动图，未记为完成')
        if operation != 'draft':
            metadata.update(_attach_generated(state, dest, result))
        update(status='done', phase='方案已保存，可继续修改和生成样片' if operation == 'draft' else '样片已生成，待审看' if state['preview'] else '媒体已生成，待审看',
               quality_review='pending', **links,
               **metadata)
        if state.get('plan_id'):
            plan = plans.load(state['plan_id'])
            jobs[plan['id']] = json.loads((ROOT/'projects/studio'/plan['id']/'status.json').read_text(encoding='utf-8'))
    except Exception as exc:
        update(status='error', phase='生成未完成', error=str(exc))


def post(handler, data, jobs):
    if not handler.path.startswith('/api/generation/'):
        return False
    if studio_edition.reject(handler, handler.path, 'POST', data):return True
    if not isinstance(data, dict):
        raise ValueError('生成请求应为 JSON 对象')
    if handler.path == '/api/generation/retry':
        job = data.get('job_id')
        if not isinstance(job, str) or not re.fullmatch(r'generation-[a-f0-9]{10}', job):
            raise ValueError('请选择生成工坊的失败任务')
        dest = plans._plain(ROOT/'projects/studio'/job)
        with QUEUE_LOCK:
            if any(s.get('kind') == 'generation' and s.get('status') in ('queued', 'running') for s in jobs.values()):
                handler.reply({'error': '请等待当前生成任务完成'}, 409); return True
            state = jobs.get(job)
            if not state or state.get('status') != 'error' or state.get('operation') != 'compose':
                raise ValueError('仅支持恢复自动制作的失败任务，已完成作品请另建版本')
            request = json.loads((dest/'render-request.json').read_text(encoding='utf-8'))
            if studio_edition.is_friend() and (request.get('kind') != 'code-animation'
                    or request.get('plan', {}).get('route') != 'code-animation'):
                handler.reply({'error': '朋友版只能续跑代码动画；此任务请在开发版继续。'}, 403)
                return True
            state.update(status='queued', phase='从已保留素材继续制作')
            state.pop('error', None)
            write(dest/'status.json', state)
            threading.Thread(target=_run, args=(jobs, job, dest, 'compose', request['kind']), daemon=True).start()
        handler.reply({'job_id': job, 'plan_id': state['plan_id']}, 202); return True
    if handler.path == '/api/generation/plan':
        if data.get('route') and not studio_edition.generation_allowed(data['route']):
            handler.reply({'error': '朋友版仅包含代码动画与白板计划。'}, 403);return True
        try:
            plan = plans.save(data) if data.get('id') else plans.create(data)
            jobs[plan['id']] = json.loads((ROOT/'projects/studio'/plan['id']/'status.json').read_text(encoding='utf-8'))
            handler.reply(plan)
        except plans.RevisionConflict as exc:
            handler.reply({'error': str(exc)}, 409)
        return True
    if handler.path not in ('/api/generation/render', '/api/generation/draft', '/api/generation/compose'):
        handler.reply({'error': '没有此生成接口'}, 404); return True
    operation = handler.path.rsplit('/', 1)[1]
    plan = plans.load(data.get('plan_id'))
    if operation in ('draft', 'compose') and data.get('revision') != plan['revision']:
        handler.reply({'error': '计划已经修改，请重新载入后再生成'}, 409); return True
    preview = data.get('preview', True)
    if not isinstance(preview, bool):
        raise ValueError('preview 应为布尔值')
    kind = data.get('kind', plan['route'])
    if studio_edition.is_friend() and (not studio_edition.generation_allowed(kind)
            or operation != 'draft' and (kind != 'code-animation' or plan['route'] != 'code-animation')):
        handler.reply({'error': '朋友版的生成工坊只渲染代码动画；白板请使用白板编辑器。'}, 403)
        return True
    payload = data.get('payload', {})
    if operation == 'render':
        if kind not in KINDS:
            raise ValueError('此路线请使用专用工作流生成')
        if kind == 'code-animation':
            import code_animation
            payload = code_animation.normalize(payload)
        else:
            payload = workers.normalize(kind, payload)
        if kind == 'blender-previs' and not workers.blender_path():
            raise ValueError('请先安装官方 Blender，再刷新生成工坊')
    else:
        import generation_automation
        if operation == 'draft' or plan['route'] in ('code-animation', 'blender-previs'):
            generation_automation.choose_writer(data.get('backend', 'auto'))
        if operation == 'compose' and plan['route'] not in ('code-animation', 'character-story', 'character-loop', 'blender-previs'):
            raise ValueError('请从对应白板或长片工作流继续生成')
    request = {'operation': operation, 'kind': kind, 'plan_id': plan['id'], 'plan': plan,
               'backend': data.get('backend', 'auto'), 'preview': preview, 'payload': payload}
    if operation == 'compose':
        request['frozen'] = generation_automation.freeze_config(plan)
        motion = data.get('motion_enabled', False)
        if not isinstance(motion, bool):
            raise ValueError('motion_enabled 应为布尔值')
        request['motion_enabled'] = motion
    with QUEUE_LOCK:
        if any(s.get('kind') == 'generation' and s.get('status') in ('queued', 'running') for s in jobs.values()):
            handler.reply({'error': '当前生成任务仍在运行，请完成后再提交，避免重复计算'}, 409); return True
        job = 'generation-' + uuid.uuid4().hex[:10]
        base = ROOT/'projects/studio'
        plans._plain(base)
        dest = base/job; dest.mkdir(parents=True)
        write(dest/'render-request.json', request)
        write(dest/'request.json', {'title': plan['title'], 'plan_id': plan['id'], 'route': kind})
        write(dest/'plan.json', plan)
        jobs[job] = {'kind': 'generation', 'workflow_kind': kind, 'operation': operation, 'status': 'queued',
                     'preview': preview, 'plan_id': plan['id'], 'plan_revision': plan['revision'],
                     'title': plan['title'], 'created_at': time.time()}
        write(dest/'status.json', jobs[job])
        threading.Thread(target=_run, args=(jobs, job, dest, operation, kind), daemon=True).start()
    handler.reply({'job_id': job, 'plan_id': plan['id']}, 202)
    return True

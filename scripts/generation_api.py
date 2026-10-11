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
import providers

QUEUE_LOCK = threading.Lock()
KINDS = {'code-animation', 'character-loop', 'blender-previs'}


def write(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def runtime():
    import generation_automation
    import renderer_health
    code_status = renderer_health.inspect(ROOT, animation=True)
    blender = workers.blender_path()
    return {'code_animation': code_status,
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
            import creative_method_worker
            import creative_custom
            handler.reply({**plans.catalog(), 'runtime': runtime(), 'creative_methods': creative_method_worker.readiness(), 'production_defaults':creative_custom.defaults()})
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
    for key in ('video', 'image', 'gif', 'webp', 'qa', 'blend', 'subtitle', 'storyboard_url', 'bundle'):
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


def _capture_services(request):
    """Resolve auto once; retries may refresh keys but keep the media recipe."""
    snapshot = _select_services(request)
    selection = providers.selection(snapshot)
    previous = request.get('service_selection')
    compared = {kind: dict(row) for kind, row in selection.items()}
    # Legacy jobs did not record Volc or the ChatGPT account. Adopt missing
    # identities once, while still checking every previously recorded choice.
    if isinstance(previous, dict) and request.get('service_selection_version', 1) == 1:
        if 'volc' not in previous:
            compared.pop('volc', None)
        if isinstance(previous.get('story'), dict) and 'account_id' not in previous['story']:
            compared.get('story', {}).pop('account_id', None)
    if 'service_selection' in request and previous != compared:
        raise ValueError('本次服务地址、模型或音色（含账号、配音资源与表达设置）与原任务不同。继续制作需恢复原服务选择；'
                         '可以更新访问密钥。使用新模型请另行生成，已有素材会保留。')
    request['service_selection'] = selection
    request['service_selection_version'] = 2
    return snapshot


def _select_services(request):
    import generation_automation as automation
    import creation_settings
    operation, plan = request['operation'], request['plan']
    if request.get('method_id') and request.get('method_mode','example')=='example' and operation == 'compose':
        return {}
    if operation == 'render':
        return {}
    if operation == 'draft':
        import character_library
        frozen=request.setdefault('frozen', {})
        if 'characters' not in frozen:frozen['characters']=character_library.freeze(plan.get('cast', []))
        if 'method_guidance' not in frozen:frozen['method_guidance']=__import__('creative_custom').guidance(plan)
    if operation == 'compose' and 'frozen' not in request:
        request['frozen'] = automation.freeze_config(plan)
    if operation == 'compose' and request.get('source')=='supplied':
        return {}
    if operation == 'draft' or plan['route'] in ('code-animation', 'blender-previs'):
        backend = request.get('backend', 'auto')
        if backend not in ('auto', 'online', 'local'):
            raise ValueError('编剧来源应为 auto、online 或 local')
        try:
            snapshot = providers.freeze(['story'] if backend != 'local' else [])
        except ValueError:
            if backend != 'auto':
                raise
            snapshot = {}
        with providers.frozen(snapshot):
            if backend == 'auto':
                try:
                    providers.configured('story')
                    backend = 'online'
                except ValueError:
                    backend = 'local'
            frozen = request.setdefault('frozen', {})
            if backend == 'local' and 'settings' not in frozen:
                frozen['settings'] = creation_settings.load()
            selected = automation.choose_writer(backend, frozen.get('settings'))
        request['backend'] = selected['backend']
        return snapshot if selected['backend'] == 'online' else {}
    import generation_visual
    backends = generation_visual._backends(plan)
    needed = {'image'}
    if plan['route'] == 'character-story':
        needed.update(('tts', 'asr'))
        if request.get('motion_enabled'):
            needed.add('video')
    selected = [kind for kind in needed if backends.get(kind) == 'online']
    if 'tts' in needed and backends.get('tts') == 'volc':
        selected.append('volc')
    snapshot = providers.freeze(selected)
    if plan['route']=='character-story' and any(c.get('reference_ids') for c in request.get('frozen',{}).get('characters',{}).values()):
        try:
            snapshot.update(providers.freeze(['story']))
        except ValueError:
            pass
        with providers.frozen(snapshot):
            writer=automation.choose_writer('auto',request['frozen']['settings'])
        request['frozen']['visual_writer']=writer['backend']
        if writer['backend']=='local':snapshot.pop('story',None)
    with providers.frozen(snapshot):
        for kind in snapshot:
            providers.configured(kind)
    return snapshot


def _run(jobs, job, dest, operation, kind, provider_snapshot=None):
    state = jobs[job]
    def update(**changes):
        state.update(changes); write(dest/'status.json', state)
    try:
        phase = '正在生成可编辑分镜' if operation == 'draft' else {
            'code-animation': '正在配音、设计画面与逐帧渲染' if operation == 'compose' else '正在逐帧渲染动画',
            'character-story': '正在生成镜头画面、配音与字幕',
            'character-loop': '正在生成角色关键姿势与循环动画',
            'blender-previs': '正在渲染几何白模与相机预演',
        }.get(kind, '正在渲染')
        update(status='running', phase=phase)
        script = 'generation_automation.py' if operation in ('draft', 'compose') else 'generation_workers.py'
        argument = operation if script == 'generation_automation.py' else kind
        command = ([str(ROOT/'tools/.venv/Scripts/python.exe'), str(ROOT/'scripts/creative_method_worker.py'), str(dest)]
                   if state.get('method_id') and state.get('method_mode','example')=='example' else
                   [str(ROOT/'tools/.venv/Scripts/python.exe'), str(ROOT/'scripts'/script), argument, str(dest)])
        if state.get('method_id'):
            update(phase='正在按所选方法制作配音、画面、字幕与交付包')
        env = os.environ.copy(); env.update(PYTHONUTF8='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HOME=str(ROOT/'cache/huggingface'))
        with (dest/'worker.log').open('w', encoding='utf-8') as log:
            options = dict(cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            process = (providers.start_worker(command, provider_snapshot, **options) if provider_snapshot is not None
                       else subprocess.Popen(command, **options))
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
            provider_snapshot = _capture_services(request)
            write(dest/'render-request.json', request)
            state.update(status='queued', phase='从已保留素材继续制作')
            state.pop('error', None)
            write(dest/'status.json', state)
            threading.Thread(target=_run, args=(jobs, job, dest, 'compose', request['kind'], provider_snapshot), daemon=True).start()
        handler.reply({'job_id': job, 'plan_id': state['plan_id']}, 202); return True
    if handler.path == '/api/generation/plan':
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
        if operation == 'compose' and plan['route'] not in ('code-animation', 'character-story', 'character-loop', 'blender-previs'):
            raise ValueError('请从对应白板或长片工作流继续生成')
    request = {'operation': operation, 'kind': kind, 'plan_id': plan['id'], 'plan': plan,
               'backend': data.get('backend', 'auto'), 'preview': preview, 'payload': payload}
    if operation == 'compose':
        request['source']=data.get('source','generate')
        if request['source'] not in ('generate','supplied'):
            raise ValueError('请选择重新生成或使用已交回镜头')
        motion = data.get('motion_enabled', False)
        if not isinstance(motion, bool):
            raise ValueError('motion_enabled 应为布尔值')
        request['motion_enabled'] = motion
        method_id=data.get('method_id') or plan.get('method_id')
        if method_id:
            if not isinstance(method_id, str) or not isinstance(data.get('asset_pack', ''), str):
                raise ValueError('方法与素材选择无效')
            import creative_custom
            creative_custom.method(method_id)
            request['method_id'] = method_id
            mode=data.get('method_mode','custom' if plan.get('method_id') else 'example')
            if mode not in ('example','custom'):raise ValueError('未知方法制作模式')
            request['method_mode']=mode
            if request['source']=='supplied' and mode=='example':
                raise ValueError('交回镜头不能同时复刻固定示例')
    provider_snapshot = _capture_services(request)
    with QUEUE_LOCK:
        if any(s.get('kind') == 'generation' and s.get('status') in ('queued', 'running') for s in jobs.values()):
            handler.reply({'error': '当前生成任务仍在运行，请完成后再提交，避免重复计算'}, 409); return True
        job = 'generation-' + uuid.uuid4().hex[:10]
        base = ROOT/'projects/studio'
        plans._plain(base)
        dest = base/job; dest.mkdir(parents=True)
        if request.get('source')=='supplied':
            import generation_delivery
            generation_delivery.freeze(plan,dest,preview)
        if request.get('method_id') and request.get('method_mode','example')=='example':
            import creative_method_worker
            creative_method_worker.freeze(request['method_id'], plan, data.get('asset_pack', ''), dest)
        write(dest/'render-request.json', request)
        write(dest/'request.json', {'title': plan['title'], 'plan_id': plan['id'], 'route': kind})
        write(dest/'plan.json', plan)
        jobs[job] = {'kind': 'generation', 'workflow_kind': kind, 'operation': operation, 'status': 'queued',
                     'preview': preview, 'plan_id': plan['id'], 'plan_revision': plan['revision'],
                     'title': plan['title'], 'created_at': time.time()}
        if request.get('method_id'):
            jobs[job]['method_id'] = request['method_id']
            jobs[job]['method_mode'] = request.get('method_mode','example')
        write(dest/'status.json', jobs[job])
        threading.Thread(target=_run, args=(jobs, job, dest, operation, kind, provider_snapshot), daemon=True).start()
    handler.reply({'job_id': job, 'plan_id': plan['id']}, 202)
    return True

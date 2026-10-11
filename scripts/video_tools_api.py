"""Saved, typed video-production pipelines with isolated workers and real outputs."""
import copy
import base64
import binascii
import io
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time
from urllib.parse import parse_qs
import uuid

from video_tools_media import ROOT, AUDIO, IMAGE, VIDEO, local_file, node, number, probe, run, ffprobe
from generation_api import write
import studio_edition
import providers

LOCK = threading.Lock()


class DraftConflict(ValueError):
    pass
COMMON = {'source', 'width', 'height', 'fps', 'music', 'music_volume'}
FIELDS = {
    'hyperframes': {'html'}, 'remotion': {'tsx', 'props', 'duration'},
    'imagegen': {'image_file', 'mode', 'prompt'},
    'ffmpeg-skill': {'cuts', 'fit', 'speed', 'volume'},
    'video-use': {'cuts', 'fit', 'speed', 'volume', 'brief', 'writer', 'asr', 'source_language', 'cues', 'subtitle_file'},
    'agent-caption': {'asr', 'source_language', 'cues', 'subtitle_file', 'burn'},
    'video-subtitle-translator': {'asr', 'source_language', 'cues', 'subtitle_file', 'translated_cues', 'language', 'writer', 'burn'},
    'video-dubbing': {'asr', 'source_language', 'cues', 'subtitle_file', 'translated_cues', 'language', 'writer', 'tts', 'voice', 'voice_speed', 'burn'},
    'app-demo-agent': {'brief', 'narration', 'tts', 'voice', 'voice_speed'},
    'browser-video-recording': {'screenshots'},
}
for _skill in ('video-use', 'agent-caption', 'video-subtitle-translator', 'video-dubbing', 'app-demo-agent'):
    FIELDS[_skill].add('local_settings')


def manifest():
    return json.loads((ROOT/'workflows/video-tools.json').read_text(encoding='utf-8'))


def catalog():
    result = manifest()
    checks = {
        'ffmpeg': (ROOT/'tools/ffmpeg.exe').is_file(),
        'ffprobe': bool(ffprobe()),
        'hyperframes': (ROOT/'tools/video-runtime/node_modules/hyperframes/bin/hyperframes.mjs').is_file() and bool(node()),
        'remotion': (ROOT/'tools/video-runtime/node_modules/@remotion/renderer/package.json').is_file() and bool(node()),
        'whisperx': (ROOT/'tools/video-skills/agent-caption/.venv-whisperx/Scripts/python.exe').is_file(),
        'qwen': (ROOT/'apps/qwen-asr/.venv/Scripts/python.exe').is_file(),
    }
    # These adapters execute our own CPU/provider code. Upstream documentation
    # is useful reference material, not a runtime requirement for manual cues.
    builtin = {'imagegen', 'agent-caption', 'video-subtitle-translator', 'video-dubbing', 'app-demo-agent'}
    for row in result['skills']:
        skill = row['id']
        if skill in builtin: row['installed'] = True
        elif skill in {'ffmpeg-skill', 'video-use'}:
            row['installed'] = (ROOT/'tools/video-skills/ffmpeg-skill/scripts/cut.py').is_file()
        elif skill == 'browser-video-recording':
            row['installed'] = (ROOT/'tools/video-skills/browser-video-recording/scripts/render_browser_demo.py').is_file()
        else: row['installed'] = checks[skill]
        row['builtin'] = skill in builtin
    import providers
    for kind in ('story', 'asr', 'tts', 'image'):
        try: providers.configured(kind); checks[kind+'_online'] = True
        except ValueError: checks[kind+'_online'] = False
    notes = {
        'hyperframes': 'HTML 源码 → MP4' if checks['hyperframes'] else '需要安装渲染组件',
        'remotion': 'React 模板 → MP4' if checks['remotion'] else '需要安装渲染组件',
        'ffmpeg-skill': '剪切、拼接、画幅与混音',
        'video-use': '手动选段可用；自动分析需要识别与编剧配置',
        'agent-caption': '可合入已有字幕；自动识别需配置识别来源',
        'video-subtitle-translator': '可导入译文；自动翻译需配置编剧来源',
        'video-dubbing': '已有译文可配音；自动翻译需配置编剧来源',
        'app-demo-agent': '录屏与旁白可合成；自动写稿需配置在线编剧',
        'browser-video-recording': '真实截图、光标、点击与缩放 → MP4',
        'imagegen': '可导入 Codex 生图；在线生图需配置接口',
    }
    for row in result['skills']: row['message'] = notes[row['id']]
    return {**result, 'checks': checks, 'edition': studio_edition.edition()}


def normalize(data, check_runtime=True, *, provider_snapshot=None):
    if not isinstance(data, dict) or set(data) - {'title', 'source', 'steps'}:
        raise ValueError('制作请求只接受 title、source、steps')
    title = data.get('title', '视频制作')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        raise ValueError('工程名称应为 1–120 字')
    steps = data.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise ValueError('请安排 1–12 个制作步骤')
    source = str(local_file(data['source'], VIDEO | IMAGE)) if data.get('source') else ''
    media_type = 'image' if source and Path(source).suffix.lower() in IMAGE else 'video' if source else None
    known_duration = probe(source)['duration'] if media_type == 'video' else None
    normalized, has_cues, cue_language = [], False, None
    installed = {r['id']: r for r in catalog()['skills']} if check_runtime else {}
    import providers
    def provider(kind):
        if not check_runtime:
            return
        if provider_snapshot is None:
            providers.configured(kind)
        else:
            if kind not in provider_snapshot:
                provider_snapshot.update(providers.freeze([kind]))
            with providers.frozen(provider_snapshot):
                providers.configured(kind)
    for step_index, step in enumerate(steps, 1):
        try:
            if not isinstance(step, dict) or set(step) - {'skill', 'options'} or not isinstance(step.get('skill'), str) or step['skill'] not in FIELDS:
                raise ValueError('请选择支持的制作步骤')
            skill = step['skill']; options = copy.deepcopy(step.get('options', {}))
            if not isinstance(options, dict) or set(options) - (FIELDS[skill] | COMMON):
                raise ValueError('步骤含不支持的参数：'+skill)
            if check_runtime and not installed[skill]['installed']:
                raise ValueError(skill+' 未安装，请运行 scripts/Install-VideoTools.ps1')
            if check_runtime and skill in {'ffmpeg-skill','video-use'} and not ffprobe():
                raise ValueError('FFprobe 未安装，无法读取剪辑素材；请运行 scripts/Install-VideoTools.ps1 补齐视频组件')
            for key in ('width', 'height'):
                if key in options:
                    value = number(options[key], key, 64, 3840)
                    if int(value) != value or value % 2: raise ValueError('画幅宽高应为偶数整数')
                    options[key] = int(value)
            for key, low, high in [('fps', 1, 60), ('duration', 1, 600), ('speed', .5, 2), ('volume', 0, 3), ('voice_speed', .5, 2), ('music_volume', 0, 1)]:
                if key in options: number(options[key], key, low, high)
            for key in ('burn',):
                if key in options and not isinstance(options[key], bool): raise ValueError(key+' 应为布尔值')
            for key in ('source', 'image_file', 'subtitle_file', 'music'):
                if options.get(key):
                    options[key] = str(local_file(options[key], {'source': VIDEO|IMAGE, 'image_file': IMAGE, 'subtitle_file': {'.srt'}, 'music': AUDIO}[key]))
            if options.get('source'):
                media_type = 'image' if Path(options['source']).suffix.lower() in IMAGE else 'video'; has_cues = False; cue_language = None
                known_duration = probe(options['source'])['duration'] if media_type == 'video' else None
            for key in ('html', 'tsx', 'prompt', 'narration', 'brief', 'language', 'source_language', 'voice'):
                if key in options and (not isinstance(options[key], str) or len(options[key]) > (300000 if key in {'html','tsx'} else 4000)):
                    raise ValueError(key+' 文本无效或过长')
            if skill in {'hyperframes', 'remotion'}:
                if skill == 'hyperframes' and not options.get('html'): raise ValueError('请提供 HyperFrames HTML 源码')
                if 'props' in options and not isinstance(options['props'], dict): raise ValueError('模板参数应为 JSON 对象')
                if check_runtime and not catalog()['checks'][skill]: raise ValueError(skill+' 渲染组件未就绪，请运行 Install-VideoTools.ps1')
                media_type, has_cues, cue_language = 'video', False, None
                known_duration = options.get('duration', 6) if skill == 'remotion' else None
            elif skill == 'imagegen':
                mode = options.get('mode', 'import')
                if mode not in {'online', 'import'}: raise ValueError('图像来源应为 online 或 import')
                if mode == 'online':
                    if not options.get('prompt'): raise ValueError('请填写生图要求')
                    provider('image')
                elif not options.get('image_file') and media_type != 'image':
                    raise ValueError('请先由 Codex 生图，再选择生成的图片文件')
                media_type, has_cues, cue_language = 'image', False, None
                known_duration = None
            elif skill == 'browser-video-recording':
                screenshots = options.get('screenshots')
                if not isinstance(screenshots, list) or not 1 <= len(screenshots) <= 40: raise ValueError('请提供 1–40 张实际浏览器截图')
                for shot in screenshots:
                    if not isinstance(shot, dict) or set(shot)-{'path','duration','x','y','zoom','click'}: raise ValueError('截图参数不正确')
                    shot['path'] = str(local_file(shot.get('path'), IMAGE))
                    number(shot.get('duration', 2), '截图停留', .5, 30)
                    number(shot.get('zoom', 1), '截图缩放', 1, 2)
                    if 'click' in shot and not isinstance(shot['click'], bool): raise ValueError('点击标记应为布尔值')
                media_type, has_cues, cue_language = 'video', False, None
                known_duration = sum(shot.get('duration', 2) for shot in screenshots)
            elif media_type != 'video':
                raise ValueError('请在 '+skill+' 之前提供视频素材或添加视频生成步骤')
            if 'cuts' in options:
                if not isinstance(options['cuts'], list) or not 1 <= len(options['cuts']) <= 100: raise ValueError('剪辑范围应为 1–100 段')
                for cut in options['cuts']:
                    if not isinstance(cut, dict) or set(cut) != {'start','end'}: raise ValueError('剪辑范围需 start 和 end')
                    number(cut['start'], '起点', 0, 14400); number(cut['end'], '终点', 0, 14400)
                    if cut['end'] <= cut['start']: raise ValueError('剪辑范围终点需晚于起点')
                    if known_duration is not None and cut['end'] > known_duration+.05:
                        raise ValueError(f'片段终点超出素材时长（{known_duration:.2f} 秒）')
            from video_tools_media import cues
            for key in ('cues', 'translated_cues'):
                if key in options: options[key] = cues(options[key], known_duration)
            need_transcript = skill in {'agent-caption','video-subtitle-translator','video-dubbing'} or skill == 'video-use' and not options.get('cuts')
            if need_transcript and not (options.get('cues') or options.get('subtitle_file') or has_cues):
                asr = options.get('asr', 'online')
                if asr == 'online': provider('asr')
                elif asr in {'whisperx', 'qwen'}:
                    studio_edition.require_local()
                    if check_runtime and not catalog()['checks'][asr]: raise ValueError('所选本地字幕引擎未安装：'+asr)
                else: raise ValueError('识别来源无效')
            if skill in {'video-subtitle-translator','video-dubbing'}:
                if not options.get('language'): raise ValueError('请选择目标语言')
            if options.get('cues') or options.get('subtitle_file'): cue_language = None
            needs_writer = skill in {'video-subtitle-translator','video-dubbing'} and not options.get('translated_cues') and cue_language != options.get('language') or skill == 'video-use' and not options.get('cuts')
            if needs_writer:
                if options.get('writer', 'online') == 'local': studio_edition.require_local()
                elif options.get('writer', 'online') == 'online': provider('story')
                else: raise ValueError('编剧来源无效')
            if skill in {'video-dubbing','app-demo-agent'}:
                tts = options.get('tts', 'windows')
                if tts == 'local': studio_edition.require_local()
                elif tts not in {'windows','edge','volc','online'}: raise ValueError('配音来源无效')
                elif check_runtime:
                    import lightweight_speech
                    if tts == 'online': provider('tts')
                    elif tts == 'volc': provider('volc')
                    with providers.frozen(provider_snapshot if provider_snapshot is not None else providers.SNAPSHOT.get()):
                        options['voice'] = lightweight_speech.validate(tts, options.get('voice',''), options.get('voice_speed',1))
            if skill == 'app-demo-agent' and not options.get('narration'): provider('story')
            if 'local_settings' in options or options.get('asr') == 'qwen' or options.get('tts') == 'local' or options.get('writer') == 'local':
                import creation_settings
                saved = options.get('local_settings')
                if saved is not None and not isinstance(saved, dict):
                    raise ValueError('本地参数快照应为对象')
                for section, defaults in creation_settings.DEFAULTS.items():
                    if saved is not None and section in saved:
                        values = saved[section]
                        if not isinstance(values, dict): raise ValueError('本地参数分组应为对象：'+section)
                        if any(key in values and isinstance(default, str) and not isinstance(values[key], str) for key, default in defaults.items()):
                            raise ValueError('本地参数中的路径和名称应为文本：'+section)
                settings = creation_settings.validate(saved or {}, check_models=False, check_voice=False)
                settings['voice'] = creation_settings.validate_voice(settings['voice'], check_reference=check_runtime and options.get('tts') == 'local')
                options['local_settings'] = settings
            normalized.append({'skill': skill, 'options': options})
            if need_transcript: has_cues = True
            if skill in {'video-subtitle-translator','video-dubbing'}: cue_language = options['language']
            if skill in {'ffmpeg-skill','video-use','app-demo-agent'}: has_cues = False; cue_language = None
            if skill in {'ffmpeg-skill','video-use'}:
                known_duration = sum(cut['end']-cut['start'] for cut in options['cuts']) if options.get('cuts') else known_duration if skill == 'ffmpeg-skill' else None
                if known_duration is not None: known_duration /= options.get('speed', 1)
            if skill == 'app-demo-agent': known_duration = None
        except (ValueError, OSError) as exc:
            raise ValueError(f'步骤 {step_index}：{exc}') from exc
    return {'title': title.strip(), 'source': source, 'steps': normalized}


def freeze(request, dest):
    frozen = copy.deepcopy(request); sources = dest/'inputs'; sources.mkdir()
    seen = {}
    def snapshot(value):
        path = Path(value)
        if value not in seen:
            target = sources/(f'{len(seen):03d}'+path.suffix.lower())
            shutil.copy2(path, target); seen[value] = str(target)
        return seen[value]
    if frozen.get('source'): frozen['source'] = snapshot(frozen['source'])
    for step in frozen['steps']:
        opts = step['options']
        for key in ('source','image_file','subtitle_file','music'):
            if opts.get(key): opts[key] = snapshot(opts[key])
        for row in opts.get('screenshots', []): row['path'] = snapshot(row['path'])
    return frozen


def project(job):
    import re
    from generation_plans import _plain
    if not isinstance(job, str) or not re.fullmatch(r'video-tools-[a-f0-9]{12}', job): raise ValueError('工程 ID 无效')
    path = _plain(ROOT/'projects/studio'/job)
    if not (path/'request.json').is_file(): raise ValueError('工程不存在')
    return path


def editable_request(value):
    # A rerun is an edit of this task, not a request to adopt today's defaults.
    return copy.deepcopy(value)


def draft_request(value):
    """Keep incomplete plans without touching media or invoking any provider."""
    if not isinstance(value, dict) or set(value) - {'title', 'source', 'steps'}:
        raise ValueError('草稿只接受 title、source、steps')
    title, source, steps = value.get('title', ''), value.get('source', ''), value.get('steps')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        raise ValueError('请先填写工程名称（1–120 字）')
    if not isinstance(source, str) or len(source) > 4096:
        raise ValueError('素材路径格式不正确')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise ValueError('草稿需要 1–12 个步骤')
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'skill', 'options'} or not isinstance(step['skill'], str) or step['skill'] not in FIELDS:
            raise ValueError('草稿中有无法识别的步骤')
        if not isinstance(step['options'], dict) or set(step['options']) - (FIELDS[step['skill']] | COMMON):
            raise ValueError('草稿中有不支持的参数')
    try:
        serialized = json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(serialized.encode('utf-8')) > 500000: raise ValueError('草稿超过 500 KB')
    except (ValueError, TypeError) as exc:
        raise ValueError('草稿包含无效数值或超出大小限制') from exc
    return {**copy.deepcopy(value), 'title': title.strip(), 'source': source}


def save_draft(data, jobs):
    if not isinstance(data, dict) or set(data) - {'id', 'revision', 'request'}:
        raise ValueError('草稿请求格式不正确')
    request = draft_request(data.get('request'))
    with LOCK:
        if data.get('id'):
            dest = project(data['id'])
            if not (dest/'draft.json').is_file(): raise ValueError('只能更新草稿；已执行的工程需另存为新草稿')
            previous = json.loads((dest/'draft.json').read_text(encoding='utf-8'))
            if type(data.get('revision')) is not int or data['revision'] != previous['revision']:
                raise DraftConflict('此草稿已在其他页面修改。当前输入已保留，请另存草稿或重新打开最新版本。')
            revision, created = previous['revision']+1, previous['created']
        else:
            dest = ROOT/'projects/studio'/('video-tools-'+uuid.uuid4().hex[:12])
            dest.mkdir(parents=True)
            revision, created = 1, time.time()
        write(dest/'draft.json', {'request':request, 'revision':revision, 'created':created})
        write(dest/'request.json', request)
        state = {'kind':'video', 'video_tools':True, 'status':'draft', 'title':request['title'],
                 'created':created, 'updated':time.time(), 'revision':revision, 'phase':'草稿已保存，可继续修改'}
        write(dest/'status.json', state)
        jobs[dest.name] = state
    return {'job_id':dest.name, 'revision':revision, 'project_url':'/video-tools?project='+dest.name}


def _execute(jobs, job, dest, request, provider_snapshot=None):
    state = jobs[job]
    try:
        frozen = freeze(request, dest)
        write(dest/'pipeline.json', frozen)
        state.update(status='running', phase='开始制作'); write(dest/'status.json', state)
        run([sys.executable, ROOT/'scripts/video_tools_worker.py', dest], dest, 'worker', timeout=7200,
            provider_snapshot=provider_snapshot)
        result = json.loads((dest/'result.json').read_text(encoding='utf-8'))
        kind = result['kind']; output = dest/result[kind]
        if kind not in {'video','image'} or not output.is_file() or output.stat().st_size <= 0:
            raise ValueError('制作未返回有效媒体文件')
        metadata = {k:v for k,v in result.items() if k in {'duration','width','height','fps'}}
        state.update(status='done', phase='制作完成，等待审片', kind=kind, quality_review='pending', **metadata)
        state[kind] = '/outputs/'+job+'/'+output.name
        state['downloads'] = [{'label':'成片' if kind=='video' else '图片','url':state[kind]}]
        for name, label in [('subtitles.srt','SRT 字幕'),('subtitles.vtt','VTT 字幕'),('stages.json','步骤与产物'),('request.json','可编辑制作方案')]:
            if (dest/name).is_file(): state['downloads'].append({'label':label,'url':'/outputs/'+job+'/'+name})
    except Exception as exc:
        failure = dest/'failure.json'
        detail = json.loads(failure.read_text(encoding='utf-8')).get('error') if failure.is_file() else str(exc)
        state.update(status='error', phase='制作未完成，素材与步骤记录已保留', error=detail)
    finally:
        write(dest/'status.json', state)


def get(handler, route, jobs=None):
    if not route.path.startswith('/api/video-tools/'): return False
    try:
        if route.path == '/api/video-tools/catalog': handler.reply(catalog())
        elif route.path == '/api/video-tools/project':
            query = parse_qs(route.query, keep_blank_values=True)
            if set(query) != {'id'} or len(query['id']) != 1: raise ValueError('请选择一个工程')
            dest = project(query['id'][0])
            state = dict((jobs or {}).get(dest.name) or json.loads((dest/'status.json').read_text(encoding='utf-8')))
            progress = dest/'progress.json'
            if state['status'] in {'running','error'} and progress.is_file():
                progress_data = json.loads(progress.read_text(encoding='utf-8'))
                state.update({k:v for k,v in progress_data.items() if k in {'step','total'}})
                if state['status'] == 'running': state['phase'] = progress_data['phase']
            editable = json.loads((dest/'request.json').read_text(encoding='utf-8'))
            if (dest/'draft.json').is_file():
                draft = json.loads((dest/'draft.json').read_text(encoding='utf-8'))
                editable, state['revision'] = draft['request'], draft['revision']
            snapshot = json.loads((dest/'pipeline.json').read_text(encoding='utf-8')) if (dest/'pipeline.json').is_file() else None
            stages = json.loads((dest/'stages.json').read_text(encoding='utf-8')) if (dest/'stages.json').is_file() else []
            for stage in stages:
                output = (dest/stage['output']).resolve()
                if output.is_relative_to(dest.resolve()) and output.is_file() and not output.is_symlink():
                    stage['url'] = '/outputs/'+dest.name+'/'+output.relative_to(dest).as_posix()
            handler.reply({'id':dest.name,'request':editable_request(editable), 'state':state, 'stages':stages,
                           'snapshot_request':editable_request(snapshot) if snapshot else None,
                           'library_id':'lib-'+hashlib.sha256(('project:'+dest.name).encode()).hexdigest()[:24]})
        else: handler.reply({'error':'制作接口不存在'},404)
    except (ValueError,OSError) as exc: handler.reply({'error':str(exc)},400)
    return True


def post(handler, data, jobs):
    if not handler.path.startswith('/api/video-tools/'): return False
    if handler.path == '/api/video-tools/import':
        handler.reply(import_media(data))
        return True
    if handler.path == '/api/video-tools/subtitles':
        from video_tools_media import read_srt
        if not isinstance(data, dict) or set(data) != {'path'}: raise ValueError('请选择一个 SRT 文件')
        handler.reply({'cues':read_srt(local_file(data['path'], {'.srt'}))})
        return True
    if handler.path == '/api/video-tools/draft':
        try: handler.reply(save_draft(data, jobs))
        except DraftConflict as exc: handler.reply({'error':str(exc)},409)
        return True
    if handler.path == '/api/video-tools/check':
        try:
            request = normalize(data)
            handler.reply({'ready':True, 'steps':len(request['steps']), 'message':'参数与依赖检查通过。未生成媒体、未调用收费推理接口。'})
        except (ValueError, OSError) as exc:
            handler.reply({'ready':False, 'message':str(exc)})
        return True
    if handler.path != '/api/video-tools/run': handler.reply({'error':'制作接口不存在'},404); return True
    provider_snapshot = {}
    request = normalize(data, provider_snapshot=provider_snapshot)
    with LOCK:
        if any(s.get('video_tools') and s.get('status') in {'queued','running'} for s in jobs.values()):
            handler.reply({'error':'已有制作任务运行，请完成后再提交'},409); return True
        job = 'video-tools-'+uuid.uuid4().hex[:12]
        dest = ROOT/'projects/studio'/job; dest.mkdir(parents=True)
        write(dest/'request.json', request)
        write(dest/'skill-sources.json', manifest())
        jobs[job] = {'kind':'video','video_tools':True,'status':'queued','title':request['title'], 'created':time.time(), 'phase':'正在冻结输入素材'}
        write(dest/'status.json', jobs[job])
        threading.Thread(target=_execute,args=(jobs,job,dest,request,provider_snapshot),daemon=True).start()
    handler.reply({'job_id':job,'project_url':'/video-tools?project='+job},202)
    return True


def import_media(data):
    """Copy a bounded browser-selected asset into local project storage."""
    if not isinstance(data, dict) or set(data) != {'name', 'base64'}:
        raise ValueError('请选择视频或图片文件')
    name, encoded = data['name'], data['base64']
    if not isinstance(name, str) or not 1 <= len(name) <= 240 or '/' in name or '\\' in name:
        raise ValueError('文件名称不正确')
    suffix = Path(name).suffix.lower()
    if suffix not in {'.mp4', '.png', '.jpg', '.jpeg', '.webp'}:
        raise ValueError('支持 MP4、PNG、JPG 和 WebP')
    if not isinstance(encoded, str) or len(encoded) > 45 * 1024**2:
        raise ValueError('文件超过 32 MB；大文件可在制作设置中填写本机路径')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('文件内容读取失败') from exc
    if not 0 < len(raw) <= 32 * 1024**2:
        raise ValueError('文件为空或超过 32 MB')
    kind = 'video' if suffix == '.mp4' else 'image'
    image = None
    if kind == 'image':
        from PIL import Image
        try:
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > 24000000:
                raise ValueError('图片不能超过 2400 万像素')
            image.load()
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError('图片无法读取') from exc
    dest = ROOT/'projects/studio'/('import-'+uuid.uuid4().hex[:12])
    dest.mkdir(parents=True)
    path = dest/('video.mp4' if kind == 'video' else 'image.png')
    try:
        if image is None:
            path.write_bytes(raw)
            info = probe(path)
            if not info.get('width') or not info.get('height'):
                raise ValueError('文件没有可读取的视频画面')
        else:
            image.save(path, format='PNG')
            info = {'width': image.width, 'height': image.height}
        url = '/outputs/'+dest.name+'/'+path.name
        write(dest/'status.json', {'kind':kind,'status':'done','imported':True,'title':Path(name).stem,
                                  'created':time.time(),kind:url,**info})
    except Exception:
        # Only remove files created in this unique import directory.
        path.unlink(missing_ok=True)
        (dest/'status.json').unlink(missing_ok=True)
        dest.rmdir()
        raise ValueError('素材无法读取，请确认文件格式与内容')
    return {'item':{'id':dest.name,'title':Path(name).stem,'media_type':kind,
                    'absolute_path':str(path),'preview_url':url,
                    'thumbnail_url':url if kind == 'image' else None,**info}}

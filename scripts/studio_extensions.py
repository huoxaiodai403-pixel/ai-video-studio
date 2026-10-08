"""Navigation, local service controls and storyboard production for the studio."""
import json
import os
import re
import socket
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import parse_qs
from prompt_library import ROOT
import providers
import creation_api
import creation_settings
import whiteboard_api
import library_api
import online_services
import generation_api
import studio_edition

SERVICES = {}
CONTROL = threading.Lock()
PYTHON = ROOT / 'tools/.venv/Scripts/python.exe'


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.15)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def launch(name, command, cwd=ROOT):
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HOME=str(ROOT/'cache/huggingface'))
    with (ROOT/'logs'/f'{name}.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(list(map(str, command)), cwd=cwd, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    SERVICES[name] = process
    return process


def handle_get(handler, route, jobs=None):
    if studio_edition.reject(handler, route.geturl(), 'GET'):return True
    if generation_api.get(handler, route, jobs):return True
    if online_services.get(handler, route):return True
    if route.path == '/api/jianying/status':
        import jianying_bridge
        try:
            query = parse_qs(route.query, keep_blank_values=True)
            if set(query) - {'project_id'} or any(len(values) != 1 for values in query.values()):
                raise ValueError('仅接受单个 project_id 参数')
            project_id = query['project_id'][0] if 'project_id' in query else None
            if project_id is not None:
                _jianying_project_id(project_id)
            handler.reply(jianying_bridge.status(project_id))
        except (ValueError, OSError, RuntimeError) as exc:
            handler.reply({'error': str(exc)}, 400)
        return True
    if library_api.get(handler, route, jobs):return True
    if route.path=='/api/music':
        import music_api
        return music_api.get(handler,route)
    if not studio_edition.is_friend():
        import investigation_api
        if investigation_api.get(handler,route):return True
    if whiteboard_api.get(handler,route):return True
    if creation_api.get(handler,route):return True
    if route.path == '/api/providers':
        handler.reply(providers.load(public=True))
        return True
    if route.path == '/api/runtime':
        handler.reply({'root': str(ROOT.resolve()), 'python': str(PYTHON),
                       'edition': studio_edition.edition(),
                       'version': (ROOT/'VERSION').read_text(encoding='utf-8').strip()})
        return True
    if route.path == '/api/services':
        handler.reply({key: {'ready': listening(port), 'starting': key in SERVICES and SERVICES[key].poll() is None}
                       for key, port in [('comfyui',8188), ('tts',7860)]})
        return True
    if route.path == '/api/project-template':
        handler.reply(json.loads((ROOT/'examples/storyboard.json').read_text(encoding='utf-8')))
        return True
    return False


def _jianying_project_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}', value):
        raise ValueError('请选择工作台中已有的工程，不接受文件路径或命令')
    return value


def handle_post(handler, data, jobs):
    if studio_edition.reject(handler, handler.path, 'POST', data):return True
    if generation_api.post(handler, data, jobs):return True
    if handler.path in ('/api/jianying/export', '/api/jianying/open'):
        import jianying_bridge
        if handler.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            handler.reply({'error': '剪映操作需要 application/json 请求'}, 415)
            return True
        exporting = handler.path.endswith('/export')
        fields = {'project_id', 'mode'} if exporting else {'project_id'}
        if not isinstance(data, dict) or set(data) - fields:
            raise ValueError('剪映操作只接受工程 ID 和草稿模式')
        project_id = data.get('project_id')
        if exporting or 'project_id' in data:
            project_id = _jianying_project_id(project_id)
        if exporting:
            mode = data.get('mode', 'auto')
            if not isinstance(mode, str) or mode not in ('auto', 'scenes', 'flattened'):
                raise ValueError('草稿模式应为 auto、scenes 或 flattened')
            result = jianying_bridge.export_project(project_id, mode=mode)
        else:
            result = jianying_bridge.open_jianying(project_id)
        handler.reply(result)
        return True
    if library_api.post(handler, data, jobs):return True
    if handler.path=='/api/music':
        import music_api
        return music_api.post(handler,data,jobs)
    if not studio_edition.is_friend():
        import investigation_api
        if investigation_api.post(handler,data,jobs):return True
    if whiteboard_api.post(handler,data,jobs):return True
    if not studio_edition.is_friend():
        import enhancement
        if enhancement.post(handler,data,jobs):return True
    if online_services.post(handler,data,jobs):return True
    if creation_api.post(handler,data,jobs):return True
    if handler.path == '/api/providers':
        providers.save(data)
        handler.reply({'message':'在线接口配置已保存；密钥已在本机加密。'})
        return True
    if handler.path == '/api/motion':
        creation=creation_settings.validate(data.get('settings',{}),check_models=False,check_voice=False)
        backend=data.get('backend','local')
        if backend not in ('local','online'):raise ValueError('未知模型来源。')
        if backend=='online':providers.configured('video')
        if backend=='local':
            import model_profiles
            model_profiles.require('motion',creation['motion']['engine'],creation['models'])
        if backend=='local' and listening(7860):
            handler.reply({'error':'请先停止配音界面。'},409)
            return True
        prompt=data.get('prompt','').strip()
        if not prompt or len(prompt)>5000:
            raise ValueError('请输入不超过 5000 字的动作描述。')
        image=Path(data['image']) if data.get('image') else None
        if backend=='local' and creation['motion']['engine']=='wan2.2-a14b' and image is None:
            raise ValueError('Wan2.2 A14B 图生视频需要首帧图片，请先生成或选择图片')
        if image and (not image.is_absolute() or not image.is_file() or image.suffix.lower() not in ('.png','.jpg','.jpeg','.webp')):
            raise ValueError('首帧应为本机已有图片的绝对路径，或留空使用文生视频。')
        steps=int(data.get('steps',20))
        if not 4<=steps<=40:raise ValueError('步数应为 4–40。')
        job='motion-'+uuid.uuid4().hex[:10];dest=ROOT/'projects/studio'/job;dest.mkdir(parents=True)
        (dest/'request.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        (dest/'settings.json').write_text(json.dumps(creation,ensure_ascii=False,indent=2),encoding='utf-8')
        jobs[job]={'status':'queued','kind':'motion','backend':backend}
        def motion():
            try:
                jobs[job]['status']='running'
                if backend=='online':providers.video(prompt,dest/'video.mp4',image)
                else:
                    command=[PYTHON,ROOT/'scripts/wan_client.py',prompt,dest/'video.mp4','--settings',dest/'settings.json']
                    if image:command+=['--image',image]
                    proc=launch(job,command)
                    if proc.wait():raise RuntimeError(f'生成失败，查看 logs/{job}.log。')
                jobs[job].update(status='done',video=f'/outputs/{job}/video.mp4')
            except Exception as exc:
                jobs[job].update(status='error',error=str(exc))
            finally:
                (dest/'status.json').write_text(json.dumps(jobs[job],ensure_ascii=False),encoding='utf-8')
        threading.Thread(target=motion,daemon=True).start()
        handler.reply({'job_id':job},202)
        return True
    if handler.path == '/api/transcribe':
        creation=creation_settings.validate(data.get('settings',{}),check_models=False,check_voice=False)
        backend=data.get('backend','local')
        if backend not in ('local','online'):raise ValueError('未知模型来源。')
        if backend=='online':providers.configured('asr')
        if backend=='local' and listening(7860):
            handler.reply({'error':'请先停止配音界面。'},409)
            return True
        audio=Path(data.get('audio',''))
        if not audio.is_absolute() or not audio.is_file() or audio.suffix.lower() not in ('.wav','.mp3','.flac','.m4a','.mp4'):
            raise ValueError('请输入本机存在的 WAV、MP3、FLAC、M4A 或 MP4 绝对路径。')
        job='asr-'+uuid.uuid4().hex[:10]
        dest=ROOT/'projects/studio'/job
        dest.mkdir(parents=True)
        (dest/'settings.json').write_text(json.dumps(creation,ensure_ascii=False,indent=2),encoding='utf-8')
        jobs[job]={'status':'queued','kind':'asr','backend':backend}
        def transcribe():
            try:
                jobs[job]['status']='running'
                if backend=='online':providers.asr(audio,dest/'transcription.json')
                else:
                    proc=launch(job,[PYTHON,ROOT/'scripts/with_gpu.py',ROOT/'apps/qwen-asr/.venv/Scripts/python.exe',
                                    ROOT/'scripts/transcribe.py',audio,'--output',dest/'transcription.json','--settings',dest/'settings.json'])
                    if proc.wait():
                        raise RuntimeError(f'识别失败，查看 logs/{job}.log；可能有其他任务正在使用显卡。')
                jobs[job].update(status='done',subtitle=f'/outputs/{job}/transcription.srt',transcript=f'/outputs/{job}/transcription.json')
            except Exception as exc:
                jobs[job].update(status='error',error=str(exc))
            finally:
                (dest/'status.json').write_text(json.dumps(jobs[job],ensure_ascii=False),encoding='utf-8')
        threading.Thread(target=transcribe,daemon=True).start()
        handler.reply({'job_id':job},202)
        return True
    if handler.path == '/api/services/tts':
        with CONTROL:
            proc = SERVICES.get('tts')
            if data.get('action') == 'stop':
                if proc and proc.poll() is None:
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,check=True)
                elif listening(7860):
                    handler.reply({'error':'配音由外部脚本启动，请关闭对应脚本窗口。'},409)
                    return True
                handler.reply({'message':'配音服务已停止，显存已释放。'})
                return True
            if listening(7860) or (proc and proc.poll() is None):
                handler.reply({'message':'配音服务已启动或正在加载。'})
                return True
            launch('tts',[PYTHON,ROOT/'scripts/with_gpu.py',ROOT/'apps/index-tts/.venv/Scripts/python.exe',
                          ROOT/'apps/index-tts/webui.py','--host','127.0.0.1','--port','7860','--fp16'],ROOT/'apps/index-tts')
            handler.reply({'message':'配音正在加载，入口显示就绪后即可打开。'},202)
        return True
    if handler.path != '/api/produce':
        return False
    spec = data.get('storyboard')
    if not isinstance(spec,dict) or not isinstance(spec.get('scenes'),list) or not 1 <= len(spec['scenes']) <= 12:
        raise ValueError('分镜应包含 1–12 个 scenes。')
    spec=creation_api.snapshot(spec)
    required=['tts','asr']+([] if spec.get('render_mode')=='whiteboard' else ['image'])
    if spec.get('motion_enabled') and spec.get('render_mode')!='whiteboard':required.append('video')
    if any(spec.get('backends',{}).get(kind,'local')=='local' for kind in required) and (listening(7860) or ('tts' in SERVICES and SERVICES['tts'].poll() is None)):
        handler.reply({'error':'请先在导航中停止配音界面，再运行使用本地模型的制片任务。'},409)
        return True
    for kind,backend in spec.get('backends',{}).items():
        if kind not in ('tts','asr','image','video') or backend not in ('local','online'):raise ValueError('未知流水线模型来源。')
        if backend=='online' and kind in required:providers.configured(kind)
    ids=[]
    if spec.get('render_mode','illustrated') not in ('illustrated','whiteboard'):
        raise ValueError('未知的制作模式。')
    for scene in spec['scenes']:
        if not isinstance(scene,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',scene.get('id','')):
            raise ValueError('镜头 id 只能包含字母、数字、下划线和短横线。')
        ids.append(scene['id'])
        if 'board_cards' in scene and (not isinstance(scene['board_cards'],list) or not 1<=len(scene['board_cards'])<=3 or any(not isinstance(x,str) or not 1<=len(x)<=20 for x in scene['board_cards'])):
            raise ValueError('白板卡片应为 1–3 条，每条 1–20 字。')
        for field in ['narration','subject','style']:
            if not isinstance(scene.get(field),str) or not 1 <= len(scene[field].strip()) <= 2000:
                raise ValueError(f'请填写镜头的 {field}，不超过 2000 字。')
        if not isinstance(scene.get('steps',20),int) or not 1 <= scene.get('steps',20) <= 60:
            raise ValueError('步数应为 1–60。')
    if len(ids) != len(set(ids)):
        raise ValueError('镜头 id 不能重复。')
    job = 'video-'+uuid.uuid4().hex[:10]
    dest=ROOT/'projects/studio'/job
    dest.mkdir(parents=True)
    from image_references import freeze_storyboard
    spec=freeze_storyboard(spec,dest)
    (dest/'storyboard.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
    jobs[job]={'status':'queued','kind':'video'}
    def run():
        try:
            jobs[job]['status']='running'
            proc=launch(job,[PYTHON,ROOT/'scripts/pipeline.py',dest])
            code=proc.wait()
            if code:
                raise RuntimeError(f'制作失败，日志：{ROOT / "logs" / (job + ".log")}')
            jobs[job].update(status='done',video=f'/outputs/{job}/video.mp4')
        except Exception as exc:
            jobs[job].update(status='error',error=str(exc))
        finally:
            (dest/'status.json').write_text(json.dumps(jobs[job],ensure_ascii=False),encoding='utf-8')
    threading.Thread(target=run,daemon=True).start()
    handler.reply({'job_id':job},202)
    return True


PAGES = {
    '/favicon.ico': ROOT/'assets/brand/studio-mark.ico',
    '/assets/brand/studio-mark.svg': ROOT/'assets/brand/studio-mark.svg',
    '/assets/brand/studio-mark.png': ROOT/'assets/brand/studio-mark.png',
    '/assets/brand/studio-mark.ico': ROOT/'assets/brand/studio-mark.ico',
    '/home': ROOT/'scripts/home.html',
    '/image': ROOT/'scripts/studio.html',
    '/library': ROOT/'scripts/library.html',
    '/gallery': ROOT/'scripts/library.html',
    '/audio-library': ROOT/'scripts/library.html',
    '/assets': ROOT/'scripts/assets.html',
    '/workflows': ROOT/'scripts/workflows.html',
    '/generation': ROOT/'scripts/generation.html',
    '/assets/generation.js': ROOT/'scripts/generation.js',
    '/assets/generation.css': ROOT/'scripts/generation.css',
    '/model-library': ROOT/'scripts/model-library.html',
    '/assets/home.js': ROOT/'scripts/home.js',
    '/assets/workflows.js': ROOT/'scripts/workflows.js',
    '/assets/hub.css': ROOT/'scripts/hub.css',
    '/assets/library.css': ROOT/'scripts/library.css',
    '/assets/library.js': ROOT/'scripts/library.js',
    '/assets/model-library.js': ROOT/'scripts/model-library.js',
    '/music': ROOT/'scripts/music.html',
    '/assets/music.js': ROOT/'scripts/music.js',
    '/assets/image_references.js': ROOT/'scripts/image_references.js',
    '/investigation': ROOT/'scripts/investigation.html',
    '/assets/investigation.js': ROOT/'scripts/investigation.js',
    '/investigation-reference.mp4': ROOT/'apps/simon-skills/skills/investigation-video/assets/sample-preview.mp4',
    '/voices': ROOT/'scripts/voices.html',
    '/assets/voices.js': ROOT/'scripts/voices.js',
    '/assets/speech_voices.js': ROOT/'scripts/speech_voices.js',
    '/assets/speech-picker.js': ROOT/'scripts/speech-picker.js',
    '/whiteboard': ROOT/'scripts/whiteboard.html',
    '/assets/whiteboard.js': ROOT/'scripts/whiteboard.js',
    '/assets/documents.css': ROOT/'scripts/documents.css',
    '/assets/document.js': ROOT/'scripts/document.js',
    '/enhance': ROOT/'scripts/enhance.html',
    '/qwen-starter.json': ROOT/'workflows/qwen-starter-ui.json',
    '/tutorial-note': ROOT/'docs/getting-started.md',
    '/models': ROOT/'scripts/local-models.html',
    '/runtime-settings': ROOT/'scripts/models.html',
    '/assets/local-models.js': ROOT/'scripts/local-models.js',
    '/novel': ROOT/'scripts/novel.html',
    '/director': ROOT/'scripts/director.html',
    '/assets/director.js': ROOT/'scripts/director.js',
    '/learn': ROOT/'scripts/learn.html',
    '/assets/creation.js': ROOT/'scripts/creation.js',
    '/assets/novel.js': ROOT/'scripts/novel.js',
    '/assets/controls.css': ROOT/'scripts/controls.css',
    '/assets/workbench.css': ROOT/'scripts/workbench.css',
    '/assets/workbench.js': ROOT/'scripts/workbench.js',
    '/settings': ROOT/'scripts/online-services.html',
    '/assets/online-services.css': ROOT/'scripts/online-services.css',
    '/assets/chatgpt-account.js': ROOT/'scripts/chatgpt-account.js',
    '/assets/online-services.js': ROOT/'scripts/online-services.js',
    '/speech': ROOT/'scripts/speech.html',
    '/motion': ROOT/'scripts/motion.html',
    '/whiteboard.mp4': ROOT/'projects/whiteboard-demo/video.mp4',
    '/subtitles': ROOT/'scripts/subtitles.html',
    '/production': ROOT/'scripts/production.html',
    '/guide': ROOT/'README.md',
    '/brief': ROOT/'workflows/制作简报模板.md',
    '/plan': ROOT/'docs/local-models.md',
    '/research': ROOT/'docs/references.md',
    '/demo.mp4': ROOT/'projects/demo/video.mp4',
    '/animation.mp4': ROOT/'projects/animation/videos/science_animation/720p30/WaveDemo.mp4',
}

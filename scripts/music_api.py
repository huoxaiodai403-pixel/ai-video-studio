"""Local background-music jobs; generated audio remains a reusable asset."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

from creation_settings import number

ROOT = Path(__file__).resolve().parents[1]
ENGINE = 'ace-step-1.5'
ENGINES = {
    ENGINE: {'name': 'ACE-Step 1.5 · 本地配乐', 'module': 'ace_bgm', 'app': 'ace-step', 'output': 'bgm'},
    'stable-audio-3-sfx': {'name': 'Stable Audio 3 · 本地音效（CPU）', 'module': 'stable_sfx',
                          'app': 'stable-audio-3', 'output': 'sfx'},
}


def readiness(engine=ENGINE):
    import importlib
    config = ENGINES[engine]
    try:
        state = importlib.import_module(config['module']).readiness()
        return {'id': engine, 'name': config['name'], 'ready': bool(state.get('ready')),
                'details': [str(row.get('name',''))+': '+str(row.get('message', ''))
                            for row in state.get('checks', [])]}
    except (ImportError, OSError, ValueError) as exc:
        return {'id': engine, 'name': config['name'], 'ready': False,
                'details': ['本地环境正在准备：'+str(exc)]}


def validate(data):
    if not isinstance(data, dict) or set(data)-{'engine','prompt','duration_seconds','bpm','seed'}:
        raise ValueError('配乐请求包含未知参数')
    engine = data.get('engine', ENGINE)
    if not isinstance(engine,str) or engine not in ENGINES:
        raise ValueError('未知音频引擎')
    sfx = engine == 'stable-audio-3-sfx'
    if sfx and 'bpm' in data:
        raise ValueError('音效不接受 BPM 参数')
    prompt = data.get('prompt', '')
    limit = 1000 if sfx else 2000
    if not isinstance(prompt,str) or not 5 <= len(prompt.strip()) <= limit or '\x00' in prompt:
        raise ValueError(f'请填写 5–{limit} 字的音频描述')
    result = {'prompt': prompt.strip(),
              'duration_seconds': number(data.get('duration_seconds',5 if sfx else 30),1 if sfx else 30,
                                         15 if sfx else 60,'音频秒数',True),
              'seed': number(data.get('seed',42),0,2147483647,'随机种子',True)}
    if not sfx:
        result.update(bpm=number(data.get('bpm',72),40,180,'BPM',True),thinking=True)
    return result


def get(handler, route):
    if route.path != '/api/music':
        return False
    handler.reply({'engines': [readiness(engine) for engine in ENGINES]})
    return True


def post(handler, data, jobs):
    if handler.path != '/api/music':
        return False
    request = validate(data)
    engine = data.get('engine', ENGINE)
    config = ENGINES[engine]
    state = readiness(engine)
    if not state['ready']:
        raise ValueError(state['name']+'尚未就绪：'+'；'.join(state['details']))
    job = 'music-'+uuid.uuid4().hex[:10]
    folder = ROOT/'projects/studio'/job
    folder.mkdir(parents=True)
    (folder/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
    label = '音效' if engine == 'stable-audio-3-sfx' else '配乐'
    jobs[job] = {'kind':'music','engine':engine,'status':'queued','created':time.time(),'phase':'等待本地'+label+'生成'}
    def save():
        temporary = folder/'status.pending.json'
        temporary.write_text(json.dumps(jobs[job],ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,folder/'status.json')
    save()
    def run():
        try:
            jobs[job].update(status='running',phase='生成本地'+label);save()
            env = os.environ.copy()
            env.update(PYTHONUTF8='1',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
            command = [str(ROOT/'apps'/config['app']/'.venv/Scripts/python.exe'),'-X','utf8',
                       str(ROOT/'scripts'/(config['module']+'.py')),str(folder),'--request',str(folder/'request.json')]
            with (folder/'generation.log').open('w',encoding='utf-8') as log:
                result = subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:
                raise RuntimeError(label+'生成失败，已保留请求与 generation.log；其他引擎不会自动替代')
            stem = config['output']
            metadata = json.loads((folder/(stem+'.metadata.json')).read_text(encoding='utf-8'))
            if metadata.get('status') != 'done' or not (folder/(stem+'.wav')).is_file():
                raise RuntimeError(label+'任务未确认完成或未输出音频')
            jobs[job].update(status='done',phase=label+'已完成，请试听',audio=f'/outputs/{job}/{stem}.wav',
                             audio_path=str(folder/(stem+'.wav')),metadata=f'/outputs/{job}/{stem}.metadata.json',
                             duration_seconds=metadata.get('duration_seconds',request['duration_seconds']))
        except Exception as exc:
            jobs[job].update(status='error',phase=label+'制作中断，请查看日志',error=str(exc))
        finally:
            save()
    threading.Thread(target=run,daemon=True).start()
    handler.reply({'job_id':job},202)
    return True

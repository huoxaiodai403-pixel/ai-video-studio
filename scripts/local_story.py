"""Local OpenAI-compatible screenwriting with the workbench GPU lock."""
import requests
from filelock import FileLock, Timeout
from creation_settings import ROOT
from comfy_client import HTTP, URL, unload


def complete(config, body):
    if not config['local_model']:
        raise ValueError('请先在本地模型与设置中选择编剧模型。')
    base = config['local_url'].rstrip('/')
    managed = base == 'http://127.0.0.1:11434/v1' and (ROOT/'apps/Ollama/ollama.exe').is_file()
    body = {**body, 'model': config['local_model']}
    if managed:
        body.update(response_format={'type': 'json_object'}, reasoning_effort='none', max_tokens=8192)
    with requests.Session() as session:
        session.trust_env = False
        try:
            session.get(base+'/models', timeout=(3, 10)).raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError('本地编剧服务未就绪，请运行工作台目录中的 Start.cmd；也可直接让 Codex 编写分镜。') from exc
        try:
            with FileLock(str(ROOT/'manifests/gpu.lock'), timeout=0):
                try:
                    queue = HTTP.get(URL+'/queue', timeout=5)
                    queue.raise_for_status()
                except requests.ConnectionError:
                    pass  # The LLM can run without ComfyUI.
                else:
                    state = queue.json()
                    if state.get('queue_running') or state.get('queue_pending'):
                        raise RuntimeError('正在生成图像或视频，请等当前任务完成后再运行本地编剧。')
                    unload()
                try:
                    response = session.post(base+'/chat/completions', json=body, timeout=(10, 600))
                    response.raise_for_status()
                    return response.json()
                finally:
                    if managed:
                        # Also release on parsing errors and failed requests.
                        session.post(base.removesuffix('/v1')+'/api/generate', json={
                            'model': config['local_model'], 'keep_alive': 0,
                        }, timeout=(5, 60)).raise_for_status()
        except Timeout as exc:
            raise RuntimeError('显卡正在进行视频、配音或编剧任务，请完成后再试。') from exc

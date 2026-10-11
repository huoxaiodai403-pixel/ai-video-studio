"""Offline ACE-Step instrumental BGM worker; import/readiness never loads torch."""
import argparse
from contextlib import nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/ace-step'
PYTHON = APP / '.venv/Scripts/python.exe'
MODELS = ROOT / 'models/ACE-Step-1.5'
PLAN = ROOT / 'examples/model-plans/ace-step-1.5.json'
PROBE = ROOT / 'manifests/ace-step.import-probe.json'
ENGINE = 'ace-step-1.5-turbo'


def _model_file_ok(row):
    """Allow only the official loader's exact model-code sync, never weight drift."""
    path = MODELS / row['name']
    if not path.is_file():
        return False
    if row['name'] in {'acestep-v15-turbo/configuration_acestep_v15.py',
                       'acestep-v15-turbo/modeling_acestep_v15_turbo.py'}:
        content = path.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
        source = APP / 'acestep/models/turbo' / path.name
        return blob == row.get('git_blob_sha1') or (source.is_file() and content == source.read_bytes())
    return path.stat().st_size == row['bytes']


def validate_request(value):
    """Validate only text and scalar controls; model/audio/script paths are fixed."""
    allowed = {'prompt', 'duration_seconds', 'seed', 'bpm', 'thinking'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('配乐请求只接受 prompt/duration_seconds/seed/bpm/thinking')
    prompt = value.get('prompt', '')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
        raise ValueError('配乐描述应为 1–2000 字的文本')
    result = {'prompt': prompt.strip(), 'duration_seconds': 45.0, 'seed': 42, 'bpm': 72, 'thinking': True}
    for key, low, high, integer in [('duration_seconds', 30, 60, False), ('seed', 0, 2147483647, True), ('bpm', 30, 300, True)]:
        number = value.get(key, result[key])
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError(f'{key} 必须是有效数字')
        if not low <= number <= high or (integer and int(number) != number):
            raise ValueError(f'{key} 应在 {low}–{high} 范围内' + ('且为整数' if integer else ''))
        result[key] = int(number) if integer else float(number)
    if not isinstance(value.get('thinking', True), bool):
        raise ValueError('thinking 必须为布尔值')
    result['thinking'] = value.get('thinking', True)
    return result


def readiness():
    """Inspect pinned model sizes and prior CPU import probe without starting models."""
    checks = [{'name': 'isolated_python', 'ready': PYTHON.is_file(), 'message': str(PYTHON)}]
    try:
        source = PROBE if PROBE.is_file() else ROOT/'manifests/ace-step-deployment-20261007.import-probe.json'
        probe = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        probe = {}
    checks.append({'name': 'dependencies', 'ready': probe.get('ready') is True,
                   'message': probe.get('message', '隔离环境尚未完成离线 CPU 导入检查')})
    try:
        plan = json.loads(PLAN.read_text(encoding='utf-8'))
        for component in plan['components']:
            required = [row for row in plan['files'] if row['name'].startswith(component + '/')]
            missing = [row['name'] for row in required if not _model_file_ok(row)]
            checks.append({'name': component, 'ready': bool(required) and not missing,
                           'message': '文件大小及模型代码来源已核对' if not missing else '缺失或内容不匹配：' + ', '.join(missing),
                           'missing': missing})
    except (OSError, ValueError, KeyError) as error:
        checks.append({'name': 'model_manifest', 'ready': False, 'message': str(error)})
    return {'ready': all(row['ready'] for row in checks), 'engine': ENGINE, 'checks': checks,
            'python': str(PYTHON), 'model_directory': str(MODELS),
            'message': '就绪仅表示依赖及文件检查通过，尚不代表本机音乐听感已验收'}


def _render(request, work):
    """Load official handlers only inside the worker's acquired GPU lock."""
    os.environ.update(ACESTEP_CHECKPOINTS_DIR=str(MODELS), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')
    from ace_bgm_runtime import render
    return render(request, work, APP, MODELS)


def _release_comfy():
    """Release an idle ComfyUI model inside the GPU lock without stopping service."""
    import requests
    from comfy_client import HTTP, URL, unload
    try:
        response = HTTP.get(URL + '/queue', timeout=(3, 5))
        response.raise_for_status()
    except requests.ConnectionError:
        return False
    queue = response.json()
    if not isinstance(queue, dict) or not {'queue_running', 'queue_pending'}.issubset(queue):
        raise RuntimeError('无法核对 ComfyUI 队列状态，未释放已有模型')
    if queue['queue_running'] or queue['queue_pending']:
        raise RuntimeError('ComfyUI 队列仍有任务，请完成后再生成配乐')
    unload()
    return True


def _audio_details(path):
    """Read actual PCM WAV geometry and checksum, without claiming listening QA."""
    with wave.open(str(path), 'rb') as stream:
        return {'duration_seconds': stream.getnframes() / stream.getframerate(),
                'sample_rate': stream.getframerate(), 'channels': stream.getnchannels(),
                'frames': stream.getnframes(), 'sample_width': stream.getsampwidth(),
                'audio_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def generate(request, project, already_locked=False):
    """Generate one 30–60s WAV in an isolated process; return saved metadata."""
    request = validate_request(request)
    state = readiness()
    if not state['ready']:
        raise RuntimeError('ACE-Step 未就绪：' + '; '.join(row['message'] for row in state['checks'] if not row['ready']))
    project = Path(project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    work = project / 'ace-step' / uuid.uuid4().hex
    work.mkdir(parents=True)
    started = time.monotonic()
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    metadata = {'engine': ENGINE, 'request': request, 'status': 'running', 'instrumental': True,
                'model_repo': plan['repo'], 'model_revision': plan['revision'], 'work_directory': str(work),
                'offline': True, 'listening_qa': 'not performed'}
    destination = project / 'bgm.metadata.json'
    def save():
        metadata['elapsed_seconds'] = round(time.monotonic() - started, 3)
        temporary = destination.with_suffix('.tmp.json')
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, destination)
    from filelock import FileLock
    try:
        with (nullcontext() if already_locked else FileLock(str(ROOT / 'manifests/gpu.lock'), timeout=0)):
            save()
            metadata['comfy_models_released'] = _release_comfy()
            source, runtime = _render(request, work)
            source = Path(source).resolve()
            if not source.is_file() or not source.is_relative_to(work):
                raise RuntimeError('ACE-Step 未返回本任务目录内的音频')
            details = _audio_details(source)
            if abs(details['duration_seconds'] - request['duration_seconds']) > 1:
                raise RuntimeError('生成音频实际时长与请求差距超过 1 秒，保留原始结果待检查')
            target = project / 'bgm.wav'
            temporary = project / 'bgm.pending.wav'
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
            metadata.update(runtime=runtime, **details, path=str(target), status='done')
            save()
    except Exception as error:
        metadata.update(status='error', error=f'{type(error).__name__}: {error}')
        save()
        raise
    return metadata


def main():
    """Print readiness or run one JSON request using the ACE virtual environment."""
    parser = argparse.ArgumentParser()
    parser.add_argument('project', nargs='?', type=Path)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(readiness(), ensure_ascii=False, indent=2))
        return
    if not args.project or not args.request:
        parser.error('生成需要 PROJECT --request REQUEST.json')
    if Path(sys.executable).resolve() != PYTHON.resolve():
        parser.error('请使用 ACE 隔离解释器：' + str(PYTHON))
    result = generate(json.loads(args.request.read_text(encoding='utf-8')), args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

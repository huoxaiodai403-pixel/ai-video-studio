"""Pinned Stable Audio 3 Small-SFX worker: CPU only, offline, no model auto-download."""
import argparse
from array import array
import hashlib
import importlib.util
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
APP = ROOT / 'apps/stable-audio-3'
PYTHON = APP / '.venv/Scripts/python.exe'
RUNTIME = APP / 'optimized/tflite'
MODELS = ROOT / 'models/Stable-Audio-3-Optimized'
PROBE = ROOT / 'manifests/stable-audio-3.import-probe.json'
ENGINE = 'stable-audio-3-sfx'
MODEL_REPO = 'stabilityai/stable-audio-3-optimized'
MODEL_REVISION = 'a0109036e3009e47ba7dcb8a2fec7ee6ac0d1ef8'
CODE_REVISION = '3a82c807b69cf4b7c5c05270011a5d5e47abac18'
MODEL_FILES = (
    ('tflite/sa3-sm-sfx/dit_fp32.tflite', 1838758544,
     '6060ecfeca34c4ab35bc1912a37e680e8cd7aab6c4bd9de1bc2655414891b8d8'),
    ('tflite/same-s/dec_w8a8.tflite', 89329616,
     '90cad5ef81e6b18eb205012aee03bc53ed59e1c17033b79a84a4612674b1e03a'),
    ('tflite/t5gemma/encoder_fp16.tflite', 563818608,
     '8530d0b3e6b9b9dcf1239145c2a853fb749708eaddbb472ff8f0802b50059372'),
)
RUNTIME_FILES = ('scripts/sa3_tflite.py', 'scripts/weights.py', 'scripts/rung_decoder.py',
                 'scripts/rung_encoder.py', 'models/defs/tflite_pipeline.py', 'models/tokenizer.model')
FIXED_PARAMETERS = {'dit': 'sm-sfx', 'decoder': 'same-s', 'dit_precision': 'fp32',
                    'decoder_precision': 'w8a8', 'steps': 8, 'cfg': 1.0, 'threads': 8}


def validate_request(value):
    if not isinstance(value, dict) or set(value) - {'prompt', 'duration_seconds', 'seed'}:
        raise ValueError('音效请求只接受 prompt/duration_seconds/seed')
    prompt = value.get('prompt', '')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1000 or '\x00' in prompt:
        raise ValueError('音效描述应为 1–1000 字的文本，不能含空字符')
    result = {'prompt': prompt.strip()}
    for name, default, low, high, integer in [('duration_seconds', 5, 1, 15, False),
                                             ('seed', 42, 0, 2147483647, True)]:
        number = value.get(name, default)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError(name + ' 必须是有效数字')
        if not low <= number <= high or (integer and number != int(number)):
            raise ValueError(f'{name} 应在 {low}–{high} 范围内' + ('且为整数' if integer else ''))
        result[name] = int(number) if integer else float(number)
    return result


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def readiness():
    """Small file/stat checks only: this never imports a model library or starts inference."""
    checks = [{'name': 'isolated_python', 'ready': PYTHON.is_file(), 'message': str(PYTHON)}]
    try:
        source = PROBE if PROBE.is_file() else ROOT/'manifests/stable-audio-3-deployment-20261007.import-probe.json'
        probe = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        probe = {}
    checks.append({'name': 'dependencies', 'ready': probe.get('ready') is True,
                   'message': probe.get('message', 'Windows CPU 隔离环境尚未通过导入检查')})
    missing_code = [name for name in RUNTIME_FILES if not (RUNTIME / name).is_file()]
    checks.append({'name': 'official_runtime', 'ready': not missing_code,
                   'message': '官方 CPU 运行代码与 tokenizer 存在' if not missing_code else '缺少：' + ', '.join(missing_code)})
    for name, size, sha in MODEL_FILES:
        path = MODELS / name
        present = path.is_file() and path.stat().st_size == size
        try:
            receipt = json.loads(path.with_name(path.name + '.verified.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            receipt = {}
        verified = present and receipt.get('sha256') == sha and receipt.get('size') == size
        checks.append({'name': name, 'ready': verified,
                       'message': '文件大小及安装校验记录齐全' if verified else '尚未完成下载或 SHA 校验：' + name})
    licenses = ('LICENSE.md', 'LICENSE_GEMMA.md')
    retained = all((MODELS / 'licenses' / name).is_file() for name in licenses)
    checks.append({'name': 'license_files', 'ready': retained,
                   'message': 'Community 与 Gemma 条款已保留；未声明商业资格' if retained else '缺少原始许可证文件'})
    return {'ready': all(row['ready'] for row in checks), 'engine': ENGINE, 'checks': checks,
            'python': str(PYTHON), 'model_directory': str(MODELS), 'device': 'cpu',
            'message': '就绪表示文件与依赖检查通过；实际生成与主观听感须另行验收'}


def _verify_artifacts():
    result = []
    for name, size, sha in MODEL_FILES:
        path = (MODELS / name).resolve()
        if not path.is_relative_to(MODELS.resolve()) or not path.is_file() or path.stat().st_size != size:
            raise RuntimeError('模型文件缺失、大小错误或越界：' + name)
        actual = _sha(path)
        if actual != sha:
            raise RuntimeError('模型 SHA256 不符：' + name)
        result.append({'name': name, 'bytes': size, 'sha256': actual})
    return result


def _offline_environment():
    os.environ.update(CUDA_VISIBLE_DEVICES='-1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
                      HF_HOME=str(ROOT / 'cache/huggingface'), DO_NOT_TRACK='1', OMP_NUM_THREADS='8')


def _render(request, work):
    """Run the fixed official CPU entrypoint with an allowlisted, offline weight resolver."""
    _offline_environment()
    runtime_paths = [str(RUNTIME), str(RUNTIME / 'scripts')]
    old_path, old_argv = list(sys.path), list(sys.argv)
    sys.path[:0] = runtime_paths
    old_weights = sys.modules.get('weights')
    source = work / 'source.wav'
    try:
        # No upstream auto-downloader is reachable: only these three paths resolve.
        mapping = {'models/' + name: (MODELS / name).resolve() for name, _, _ in MODEL_FILES}

        def local_only(name, verbose=True):
            if name not in mapping or not mapping[name].is_file():
                raise RuntimeError('离线音效运行不能下载或加载未登记模型：' + str(name))
            return mapping[name]

        weight_spec = importlib.util.spec_from_file_location('weights', RUNTIME / 'scripts/weights.py')
        weights = importlib.util.module_from_spec(weight_spec)
        weight_spec.loader.exec_module(weights)
        weights.ensure_local = local_only
        weights.is_present = lambda name: name in mapping and mapping[name].is_file()
        sys.modules['weights'] = weights
        runtime_spec = importlib.util.spec_from_file_location('_stable_sfx_official', RUNTIME / 'scripts/sa3_tflite.py')
        runtime = importlib.util.module_from_spec(runtime_spec)
        runtime_spec.loader.exec_module(runtime)

        # The bundled tokenizer is small; avoid silently truncating the user's text.
        tokenizer = runtime.P.Tokenizer()
        tokens = len(tokenizer.sp.Encode(request['prompt']))
        if tokens > runtime.P.COND_TOKENS:
            raise ValueError(f'音效描述包含 {tokens} 个 token，超过模型 {runtime.P.COND_TOKENS} 上限，请缩短描述')
        from ai_edge_litert.compiled_model import Options
        from ai_edge_litert.hardware_accelerator import HardwareAccelerator
        from ai_edge_litert.cpu_options import CpuOptions
        if Options(cpu_options=CpuOptions(num_threads=8)).hardware_accelerators != HardwareAccelerator.CPU:
            raise RuntimeError('LiteRT 默认执行设备不是 CPU，拒绝加载模型')
        sys.argv = [str(RUNTIME / 'scripts/sa3_tflite.py'), '--dit', 'sm-sfx', '--decoder', 'same-s',
                    '--dit-precision', 'fp32', '--decoder-precision', 'w8a8', '--steps', '8', '--cfg', '1',
                    '--threads', '8', '--free-models', '--seconds', str(request['duration_seconds']),
                    '--seed', str(request['seed']), '--prompt=' + request['prompt'], '--out=' + str(source)]
        try:
            runtime.main()
        except SystemExit as error:
            raise RuntimeError('官方 CPU 运行器退出：' + str(error)) from error
        return source, {'parameters': dict(FIXED_PARAMETERS), 'prompt_tokens': tokens,
                        'runtime_source_sha256': {name: _sha(RUNTIME / name) for name in RUNTIME_FILES},
                        'weight_resolution': 'fixed local allowlist; auto-download disabled'}
    finally:
        sys.path[:] = old_path
        sys.argv[:] = old_argv
        if old_weights is None:
            sys.modules.pop('weights', None)
        else:
            sys.modules['weights'] = old_weights


def _audio_details(path):
    with wave.open(str(path), 'rb') as audio:
        rate, channels, width, frames = audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()
        if (rate, channels, width) != (44100, 2, 2) or frames < 1:
            raise RuntimeError('官方音效输出必须是非空 44.1kHz 双声道 PCM16 WAV')
        samples = array('h', audio.readframes(frames))
    if sys.byteorder != 'little':
        samples.byteswap()
    if len(samples) != frames * channels:
        raise RuntimeError('音效 WAV 数据截断')
    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768
    if peak == 0:
        raise RuntimeError('音效输出完全静音，不能标记为完成')
    return {'sample_rate': rate, 'channels': channels, 'sample_width': width, 'frames': frames,
            'duration_seconds': frames / rate, 'audio_sha256': _sha(path), 'peak': peak / 32768,
            'rms': rms, 'near_full_scale_samples': sum(abs(value) >= 32760 for value in samples)}


def generate(request, project):
    request = validate_request(request)
    project = Path(project).resolve()
    if not project.is_relative_to((ROOT / 'projects').resolve()):
        raise ValueError('音效输出必须位于工作台 projects 目录内')
    state = readiness()
    if not state['ready']:
        raise RuntimeError('Stable Audio 音效尚未就绪：' + '; '.join(row['message'] for row in state['checks'] if not row['ready']))
    project.mkdir(parents=True, exist_ok=True)
    work = project / 'stable-sfx' / uuid.uuid4().hex
    if not work.resolve().is_relative_to(project):
        raise ValueError('音效工作目录越界')
    work.mkdir(parents=True)
    if not work.resolve().is_relative_to(project):
        raise ValueError('音效工作目录越界')
    started = time.monotonic()
    metadata = {'engine': ENGINE, 'request': request, 'status': 'running', 'device': 'cpu', 'offline': True,
                'model_repo': MODEL_REPO, 'model_revision': MODEL_REVISION, 'code_revision': CODE_REVISION,
                'parameters': dict(FIXED_PARAMETERS), 'work_directory': str(work),
                'listening_qa': 'not performed', 'commercial_status': 'not asserted',
                'licenses': [str(MODELS / 'licenses' / name) for name in ('LICENSE.md', 'LICENSE_GEMMA.md')]}
    destination = project / 'sfx.metadata.json'

    def save():
        metadata['elapsed_seconds'] = round(time.monotonic() - started, 3)
        temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, destination)

    from filelock import FileLock
    (ROOT / 'manifests').mkdir(exist_ok=True)
    try:
        # CPU jobs serialize with each other without taking the model GPU lock.
        with FileLock(str(ROOT / 'manifests/stable-sfx-cpu.lock'), timeout=0):
            save()
            metadata['artifacts'] = _verify_artifacts()
            _offline_environment()
            source, runtime = _render(request, work)
            source = Path(source).resolve()
            if not source.is_relative_to(work.resolve()) or not source.is_file():
                raise RuntimeError('音效运行器未返回本任务目录内的音频')
            details = _audio_details(source)
            if abs(details['frames'] - round(request['duration_seconds'] * 44100)) > 1:
                raise RuntimeError('音效实际时长与请求不符，已保留原始输出')
            target = project / 'sfx.wav'
            pending = project / ('sfx.' + uuid.uuid4().hex + '.pending.wav')
            shutil.copy2(source, pending)
            os.replace(pending, target)
            metadata.update(status='done', path=str(target), runtime=runtime, **details)
            save()
    except Exception as error:
        metadata.update(status='error', error=f'{type(error).__name__}: {error}')
        save()
        raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description='CPU-only offline Stable Audio 3 Small-SFX worker')
    parser.add_argument('project', type=Path, nargs='?')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(readiness(), ensure_ascii=False, indent=2))
        return
    if not args.project or not args.request:
        parser.error('生成需要 PROJECT --request REQUEST.json')
    if Path(sys.executable).resolve() != PYTHON.resolve():
        parser.error('请使用 Stable Audio 隔离解释器：' + str(PYTHON))
    project, request = args.project.resolve(), args.request.resolve()
    if not project.is_relative_to((ROOT / 'projects').resolve()) or not request.is_relative_to(project):
        parser.error('项目和请求 JSON 必须位于本任务的工作台 projects 目录内')
    if not request.is_file() or request.stat().st_size > 64 * 1024:
        parser.error('请求 JSON 不存在或超过 64 KiB')
    result = generate(json.loads(request.read_text(encoding='utf-8')), project)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

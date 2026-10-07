"""Decode a verified Wan latent again, without loading UNet/CLIP or sampling.

Example (only prepares files; no ComfyUI request or GPU work):
  python scripts/redecode_video.py PROJECT --temporal-size 16 --temporal-overlap 4 --prepare-only
Every invocation creates a separate comparison directory under PROJECT/redecode.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import time
import uuid

from filelock import FileLock
from comfy_client import ROOT, HTTP, URL


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def save_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def read_json(path):
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('缺少项目 JSON 或文件超过 8MiB：' + str(path))
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('项目 JSON 必须是对象：' + str(path))
    return value


def validate_temporal(size, overlap):
    for name, value, minimum in [('temporal_size', size, 8), ('temporal_overlap', overlap, 4)]:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 4096 or value % 4:
            raise ValueError(f'{name} 必须是 {minimum}–4096 内的 4 的倍数（输出帧单位）')
    # Avoid ComfyUI silently altering overlap when it exceeds half the window.
    if overlap > size // 2:
        raise ValueError('temporal_overlap 不得超过 temporal_size 的一半')


def load_source(project):
    project = Path(project).resolve()
    if not project.is_relative_to((ROOT / 'projects').resolve()):
        raise ValueError('项目必须位于工作台 projects 内')
    metadata = read_json(project / 'video.generation.json')
    graph = read_json(project / 'video.workflow.json')
    engine = metadata.get('engine')
    if engine not in ('wan2.2-a14b', 'wan2.2-5b'):
        raise ValueError('只接受已有 Wan A14B 或 5B 项目 latent')
    # Failed decode jobs with a saved latent are useful diagnostics, but never
    # consume a snapshot while the producer is still writing it.
    if metadata.get('status') not in ('done', 'error', 'rejected', 'timeout'):
        raise ValueError('原任务尚未结束，不能读取正在生成的 latent')
    latent = (project / 'video.latent').resolve()
    if not latent.is_relative_to(project) or not latent.is_file():
        raise ValueError('缺少项目内 video.latent 快照或路径越界')
    expected = metadata.get('latent_sha256', '')
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected):
        raise ValueError('原任务未记录有效 latent_sha256，拒绝重解码')
    actual = sha256(latent)
    if actual != expected.lower():
        raise ValueError('video.latent SHA256 不符，拒绝重解码')
    for key in ('width', 'height', 'frames'):
        if isinstance(metadata.get(key), bool) or not isinstance(metadata.get(key), int) or metadata[key] < 1:
            raise ValueError('原任务几何不合法：' + key)
    fps = metadata.get('fps')
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 0 < fps <= 120:
        raise ValueError('原任务帧率不合法')
    vae_nodes = [row for row in graph.values() if isinstance(row, dict) and row.get('class_type') == 'VAELoader']
    if len(vae_nodes) != 1:
        raise ValueError('原工作流必须含唯一 VAELoader')
    vae = vae_nodes[0].get('inputs', {}).get('vae_name')
    if (not isinstance(vae, str) or not vae or ':' in vae or '\\' in vae
            or PurePosixPath(vae).is_absolute() or any(part in ('.', '..') for part in vae.split('/'))):
        raise ValueError('原工作流 VAE 名称不是安全的模型相对路径')
    # Read only the safetensors header: do not import torch or materialize tensors.
    with latent.open('rb') as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError('latent 文件头不完整')
        length = struct.unpack('<Q', prefix)[0]
        if not 2 <= length <= 8 * 1024 * 1024 or length + 8 > latent.stat().st_size:
            raise ValueError('latent 文件头长度不合法')
        header = json.loads(stream.read(length))
    tensor = header.get('latent_tensor', {})
    shape = tensor.get('shape', [])
    spatial, channels = (8, 16) if engine == 'wan2.2-a14b' else (16, 48)
    expected_shape = [1, channels, (metadata['frames'] + 3) // 4,
                      metadata['height'] // spatial, metadata['width'] // spatial]
    if (metadata['frames'] % 4 != 1 or metadata['height'] % spatial or metadata['width'] % spatial
            or shape != expected_shape or tensor.get('dtype') not in ('F32', 'F16', 'BF16')
            or 'latent_format_version_0' not in header):
        raise ValueError('latent 形状/格式与原任务引擎、帧数或尺寸不符')
    return {'project': str(project), 'latent': str(latent), 'latent_sha256': actual,
            'engine': engine, 'vae_name': vae, 'shape': shape, 'dtype': tensor['dtype'],
            'width': metadata['width'], 'height': metadata['height'],
            'frames': metadata['frames'], 'fps': fps}


def workflow(source, input_name, prefix, temporal_size, temporal_overlap):
    validate_temporal(temporal_size, temporal_overlap)
    if not re.fullmatch(r'redecode-[0-9a-f]{32}\.latent', input_name):
        raise ValueError('只允许本工具生成的唯一 latent 输入文件名')
    return {
        '1': {'class_type': 'LoadLatent', 'inputs': {'latent': input_name}},
        '2': {'class_type': 'VAELoader', 'inputs': {'vae_name': source['vae_name']}},
        '3': {'class_type': 'VAEDecodeTiled', 'inputs': {
            'samples': ['1', 0], 'vae': ['2', 0], 'tile_size': 256, 'overlap': 64,
            'temporal_size': temporal_size, 'temporal_overlap': temporal_overlap}},
        '4': {'class_type': 'SaveImage', 'inputs': {'images': ['3', 0], 'filename_prefix': prefix}},
    }


def prepare(project, temporal_size=128, temporal_overlap=16):
    validate_temporal(temporal_size, temporal_overlap)
    source = load_source(project)
    identifier = uuid.uuid4().hex
    parent = Path(source['project'])
    destination = parent / 'redecode' / f't{temporal_size}-o{temporal_overlap}-{identifier[:12]}'
    if not destination.resolve().is_relative_to(parent):
        raise ValueError('诊断目录越界')
    destination.mkdir(parents=True, exist_ok=False)
    input_name = 'redecode-' + identifier + '.latent'
    graph = workflow(source, input_name, 'AI-Video/ReDecode/' + identifier,
                     temporal_size, temporal_overlap)
    plan = {'operation': 'redecode', 'status': 'prepared', 'source': source,
            'directory': str(destination), 'input_name': input_name,
            'temporal_size': temporal_size, 'temporal_overlap': temporal_overlap,
            'spatial_tile': 256, 'spatial_overlap': 64, 'samples_are_resampled': False,
            'gpu_execution_started': False}
    save_json(destination / 'video.workflow.json', graph)
    save_json(destination / 'video.generation.json', plan)
    return plan, graph


def require_empty_queue():
    response = HTTP.get(URL + '/queue', timeout=(3, 10))
    response.raise_for_status()
    value = response.json()
    if (not isinstance(value, dict) or not isinstance(value.get('queue_running'), list)
            or not isinstance(value.get('queue_pending'), list)):
        raise RuntimeError('无法核对 ComfyUI 队列，未提交诊断任务')
    if value['queue_running'] or value['queue_pending']:
        raise RuntimeError('ComfyUI 队列非空，未提交诊断任务')


def output_frames(record, destination, source):
    from PIL import Image
    entries = record.get('outputs', {}).get('4', {}).get('images', [])
    if not isinstance(entries, list) or len(entries) != source['frames']:
        raise RuntimeError(f"实际输出帧数 {len(entries) if isinstance(entries, list) else 'invalid'} 与原任务 {source['frames']} 不符")
    base = (ROOT / 'apps/ComfyUI/output').resolve()
    frames = destination / 'frames'
    frames.mkdir(exist_ok=False)
    seen = set()
    for index, entry in enumerate(entries):
        path = (base / entry.get('subfolder', '') / entry['filename']).resolve()
        if (entry.get('type') != 'output' or not path.is_relative_to(base)
                or path.suffix.lower() != '.png' or path in seen or not path.is_file()):
            raise ValueError('ComfyUI 图像输出路径越界、重复或不存在')
        seen.add(path)
        with Image.open(path) as image:
            image.load()
            if image.size != (source['width'], source['height']):
                raise RuntimeError('实际输出帧尺寸与原项目不一致')
        shutil.copy2(path, frames / f'{index:05d}.png')
    return frames, len(entries)


def run(plan, graph, timeout=1200):
    destination = Path(plan['directory'])
    started = time.monotonic()
    def save():
        plan['elapsed_seconds'] = round(time.monotonic() - started, 3)
        save_json(destination / 'video.generation.json', plan)
    try:
        with FileLock(str(ROOT / 'manifests/gpu.lock'), timeout=0):
            require_empty_queue()
            # Source may have changed between preparation and acquiring the lock.
            checked = load_source(plan['source']['project'])
            if checked != plan['source']:
                raise ValueError('准备后原项目 latent 或参数已变化，拒绝重解码')
            folder = (ROOT / 'apps/ComfyUI/input').resolve()
            target = folder / plan['input_name']
            with Path(checked['latent']).open('rb') as source_file, target.open('xb') as output:
                shutil.copyfileobj(source_file, output)
            if sha256(target) != checked['latent_sha256']:
                raise ValueError('ComfyUI 输入 latent 复制后 SHA256 不符')
            plan.update(status='submitting', input_path=str(target), input_sha256=sha256(target))
            save()
            response = HTTP.post(URL + '/prompt', json={'prompt': graph, 'client_id': uuid.uuid4().hex}, timeout=30)
            response.raise_for_status()
            pid = response.json()['prompt_id']
            plan.update(status='running', prompt_id=pid, gpu_execution_started=True)
            save()
            deadline = time.monotonic() + timeout
            record = None
            while time.monotonic() < deadline:
                response = HTTP.get(URL + '/history/' + pid, timeout=30)
                response.raise_for_status()
                record = response.json().get(pid)
                if record:
                    save_json(destination / 'video.history.json', record)
                    state = record.get('status', {})
                    if state.get('status_str') in ('error', 'interrupted'):
                        raise RuntimeError('ComfyUI 重解码失败：' + json.dumps(state, ensure_ascii=False))
                    if state.get('completed') or state.get('status_str') == 'success':
                        break
                time.sleep(2)
            else:
                plan['queue_may_still_be_running'] = True
                raise TimeoutError('重解码等待超时；ComfyUI 可能仍在执行，检查队列后再启动其他 GPU 任务')
            frames, count = output_frames(record, destination, checked)
            command = [str(ROOT / 'tools/ffmpeg.exe'), '-v', 'error', '-n', '-framerate', str(checked['fps']),
                       '-i', str(frames / '%05d.png'), '-frames:v', str(count), '-c:v', 'libx264',
                       '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart', str(destination / 'video.mp4')]
            with (destination / 'encoding.log').open('w', encoding='utf-8') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            plan.update(status='done', actual_frames=count, width=checked['width'], height=checked['height'],
                        fps=checked['fps'], duration_seconds=count / checked['fps'],
                        video_sha256=sha256(destination / 'video.mp4'), encoding_command=command,
                        visual_qa='not performed')
            save()
            # Do not clear another caller's queue or cache if it was submitted
            # outside the shared GPU lock while this diagnostic was running.
            try:
                require_empty_queue()
                response = HTTP.post(URL + '/free', json={'unload_models': True, 'free_memory': True}, timeout=30)
                response.raise_for_status()
                plan['models_released'] = True
            except Exception as error:
                plan['models_released'] = False
                plan['release_note'] = str(error)
            save()
    except Exception as error:
        plan.update(status='error', error=f'{type(error).__name__}: {error}')
        save()
        raise
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--temporal-size', type=int, default=128)
    parser.add_argument('--temporal-overlap', type=int, default=16)
    parser.add_argument('--prepare-only', action='store_true', help='SHA/header/graph checks only; never contact ComfyUI')
    args = parser.parse_args()
    plan, graph = prepare(args.project, args.temporal_size, args.temporal_overlap)
    if not args.prepare_only:
        run(plan, graph)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

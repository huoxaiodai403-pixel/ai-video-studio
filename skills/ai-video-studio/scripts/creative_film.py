#!/usr/bin/env python3
"""Narrated creative films through the existing Studio APIs, with resumable receipts.

No GPU, cloud provider, web server or upstream executable is started here.
Author scene.html with <!-- CREATIVE_FILM --> and window.renderFrame(seconds).
The injected CREATIVE_FILM contains real speech boundaries, not estimated timings.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import wave
import zipfile

from creative_video import catalog, recipe, source_path, verify_sources
from studio_client import Client, StudioError, find_root, load_payload, output, save_download, REQUEST_LIMIT

MARKER = '<!-- CREATIVE_FILM -->'
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def norm(text):
    return ''.join(c.lower() for c in text if c.isalnum())


def finite(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ' 必须是有限数值')
    if not low <= value <= high or integer and int(value) != value:
        raise ValueError(name + ' 超出支持范围')
    return value


def validate(spec):
    allowed = {'title', 'width', 'height', 'fps', 'speech', 'scenes', 'scene_html', 'assets', 'style', 'brief', 'tail', 'audio_bed'}
    if not isinstance(spec, dict) or set(spec) - allowed:
        raise ValueError('成片规格含未知字段')
    result = json.loads(json.dumps(spec, allow_nan=False))
    for key, maximum in [('title', 100), ('style', 2000), ('brief', 8000)]:
        value = result.get(key, '')
        if not isinstance(value, str) or len(value) > maximum or key == 'title' and not value.strip():
            raise ValueError(key + ' 文本无效')
    for key, default, high in [('width', 1280, 1920), ('height', 720, 1920), ('fps', 25, 30)]:
        result[key] = int(finite(result.get(key, default), key, 1 if key == 'fps' else 256, high, True))
    if result['width'] % 2 or result['height'] % 2 or result['width'] * result['height'] > 2073600:
        raise ValueError('画幅需偶数，最多 1920×1080 像素')
    result['tail'] = finite(result.get('tail', .6), 'tail', .1, 2)
    voice = result.setdefault('speech', {'backend': 'windows', 'voice_id': '', 'speed': 1})
    if not isinstance(voice, dict) or set(voice) - {'backend', 'voice_id', 'speed'} or voice.get('backend') != 'windows':
        raise ValueError('此连续配音适配器当前使用 Windows；其他声音请用既有媒体流程，不会自动切换')
    if not isinstance(voice.get('voice_id', ''), str):
        raise ValueError('voice_id 应为文字')
    finite(voice.get('speed', 1), '语速', .5, 2)
    scenes = result.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 16:
        raise ValueError('需要 1–16 个语义镜头')
    seen = set()
    for scene in scenes:
        if not isinstance(scene, dict) or set(scene) - {'id', 'narration', 'visual', 'action', 'camera'}:
            raise ValueError('镜头只接受 id、narration、visual、action、camera')
        identity = scene.get('id', '')
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', identity) or identity in seen:
            raise ValueError('镜头 ID 必须唯一且为小写字母/数字/连字符')
        seen.add(identity)
        for key in ('narration', 'visual', 'action', 'camera'):
            value = scene.get(key, '')
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('镜头文本无效：' + key)
        if not norm(scene.get('narration', '')) or not scene.get('visual', '').strip():
            raise ValueError('每镜需要原句和具体画面')
    if len(''.join(s['narration'] for s in scenes)) > 4000:
        raise ValueError('整段口播最多 4000 字；成片实际时长上限 60 秒')
    if not isinstance(result.get('scene_html'), str):
        raise ValueError('请指定相对规格文件的 scene_html')
    assets = result.setdefault('assets', {})
    if not isinstance(assets, dict) or len(assets) > 12:
        raise ValueError('最多 12 个内嵌图像素材')
    for identity, path in assets.items():
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', identity) or not isinstance(path, str):
            raise ValueError('素材需要安全 ID 和相对文件路径')
        if Path(path).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
            raise ValueError('素材应为 PNG/JPEG/WebP')
    bed = result.get('audio_bed')
    if bed is not None:
        if not isinstance(bed, dict) or set(bed) - {'path', 'gain', 'loop', 'credit'}:
            raise ValueError('背景音仅接受 path、gain、loop、credit')
        if not isinstance(bed.get('path'), str) or Path(bed['path']).suffix.lower() != '.wav':
            raise ValueError('背景音需要相对路径的 WAV 文件')
        bed['gain'] = finite(bed.get('gain', .15), '背景音增益', 0, 1)
        if not isinstance(bed.get('loop', False), bool):
            raise ValueError('背景音 loop 应为布尔值')
        if not isinstance(bed.get('credit', ''), str) or len(bed.get('credit', '')) > 2000:
            raise ValueError('背景音来源说明无效')
    return result


def caption_groups(words, maximum=18):
    """Balance at real word boundaries; avoid a tiny trailing subtitle cue."""
    sentences, pending = [], []
    for word in words:
        if len(norm(word['text'])) > maximum:
            raise ValueError('合成器返回超过 18 字的整词，不能伪造拆词时间')
        pending.append(word)
        if word['text'].rstrip().endswith(('。', '！', '？', '；', '.', '!', '?', ';')):
            sentences.append(pending); pending = []
    if pending: sentences.append(pending)
    groups = []
    for sentence in sentences:
        while sum(len(norm(w['text'])) for w in sentence) > maximum:
            total = sum(len(norm(w['text'])) for w in sentence)
            target = total / math.ceil(total / maximum)
            candidates, count = [], 0
            for index, word in enumerate(sentence[:-1], 1):
                count += len(norm(word['text']))
                if count > maximum: break
                if count >= 4 and total - count >= 4:
                    penalty = abs(count - target) - (2 if word['text'].rstrip().endswith(('，', '：', ',', ':')) else 0)
                    candidates.append((penalty, index))
            if not candidates:
                raise ValueError('合成整词无法组成清楚的短字幕，请调整语句或合成分词；不伪造拆词时间')
            cut = min(candidates)[1]
            groups.append(sentence[:cut]); sentence = sentence[cut:]
        if sentence: groups.append(sentence)
    return [{'text': ''.join(w['text'] for w in group), 'start': group[0]['start'], 'end': group[-1]['end']}
            for group in groups]


def build_timeline(scenes, words, seconds, fps, tail=.6):
    """Split only on a real synthesis boundary, never interpolate missing words."""
    finite(seconds, '配音时长', .1, 60)
    if not isinstance(words, list) or not words:
        raise ValueError('缺少真实逐词时间戳')
    if norm(''.join(s['narration'] for s in scenes)) != norm(''.join(w.get('text', '') for w in words)):
        raise ValueError('时间戳原文与口播不一致，已停止，不能按字数估时')
    positions, cursor, previous = {0: 0}, 0, -1.0
    for index, word in enumerate(words):
        start = finite(word.get('start'), '词起点', 0, seconds)
        end = finite(word.get('end'), '词终点', 0, seconds + .001)
        count = len(norm(word.get('text', '')))
        if not count or start < previous or end <= start:
            raise ValueError('逐词时间轴无效')
        previous = end
        cursor += count
        positions[cursor] = index + 1
    timeline, captions, cursor = [], [], 0
    for index, scene in enumerate(scenes):
        start_index = positions.get(cursor)
        cursor += len(norm(scene['narration']))
        end_index = positions.get(cursor)
        if start_index is None or end_index is None:
            raise ValueError('镜头分界落在一个合成词内部；请按完整句子划分镜头')
        start = 0 if index == 0 else words[start_index]['start']
        end = words[end_index]['start'] if end_index < len(words) else seconds
        if end - start < .4:
            raise ValueError('镜头短于 0.4 秒，请合并语义镜头')
        timeline.append({**scene, 'start': start, 'end': end, 'duration': end - start})
        captions.extend(caption_groups(words[start_index:end_index]))
    duration = math.ceil((seconds + tail) * fps - 1e-9) / fps
    if duration > 60:
        raise ValueError('真实音轨加收尾超过 60 秒；请拆章，不能截断口播')
    return {'scenes': timeline, 'captions': captions, 'duration': duration,
            'speech_duration': seconds, 'timing': 'synthesis-word-starts; not forced alignment'}


def stamp(value):
    ms = round(value * 1000)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def plan_request(spec, timeline, method):
    # Generation plan voice_id is a LOCAL preset ID, never a Windows voice name.
    # Exact Windows selection/rate remain frozen in spec, audio and delivery metadata.
    return {'title': spec['title'], 'route': 'code-animation',
            'brief': spec.get('brief', '') + '\n创作方法：' + recipe(method)['title'],
            'style': spec.get('style', ''), 'voice_id': '', 'speech_backend': 'windows', 'image_backend': 'online',
            'shots': [{**{key: row[key] for key in ('id', 'narration', 'visual', 'action', 'camera') if key in row},
                       'duration': round(row['duration'], 3)} for row in timeline['scenes']]}


def compose_html(template, timeline, spec, assets, helper):
    if template.count(MARKER) != 1:
        raise ValueError('动画源码须且仅须包含一个 <!-- CREATIVE_FILM -->')
    data = {**timeline, 'width': spec['width'], 'height': spec['height'], 'title': spec['title']}
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    images = []
    for identity, (suffix, contents) in assets.items():
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}[suffix]
        images.append(f'<img hidden id="film-asset-{identity}" src="data:{mime};base64,{base64.b64encode(contents).decode()}">')
    return template.replace(MARKER, ''.join(images) + '<script>window.CREATIVE_FILM=' + encoded + ';\n' + helper + '</script>')


@contextmanager
def locked(project):
    """OS lock releases after a crash; never run two dispatchers for one project."""
    with (project / '.run.lock').open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError('此工程已有制作进程，请使用 status 查看') from exc
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream, fcntl.LOCK_UN)


def prepare(root, item, spec_file, project, base):
    spec = validate(load_payload(spec_file))
    source = spec_file.resolve().parent
    scene = source_path(source, spec['scene_html'])
    template = scene.read_text(encoding='utf-8')
    # Validate authored HTML before creating a speech job (the marker is inert).
    import code_animation
    code_animation.normalize({'html': template, 'width': spec['width'], 'height': spec['height'], 'duration': 1})
    if template.count(MARKER) != 1:
        raise ValueError('动画源码缺少唯一 CREATIVE_FILM 标记')
    inputs = {'scene-template.html': scene, 'creative-canvas.js': HERE / 'creative-canvas.js'}
    for identity, relative in spec['assets'].items():
        path = source_path(source, relative)
        if not path.is_file() or not 0 < path.stat().st_size <= 280000:
            raise ValueError('内嵌视频素材需非空且不超过 280 KB：' + relative)
        inputs['assets/' + identity + path.suffix.lower()] = path
    if sum(p.stat().st_size for p in inputs.values()) * 1.4 > 400000:
        raise ValueError('自包含源码和图像过大；请为视频准备较小的素材副本，保留原文件')
    if spec.get('audio_bed'):
        bed_path = source_path(source, spec['audio_bed']['path'])
        if not bed_path.is_file() or not 0 < bed_path.stat().st_size <= 50_000_000:
            raise ValueError('背景音需非空且不超过 50 MB')
        with wave.open(str(bed_path), 'rb') as bed:
            if bed.getnchannels() not in (1, 2) or bed.getsampwidth() != 2 or bed.getnframes() == 0:
                raise ValueError('背景音需要非空 16 位 PCM 单声道或双声道 WAV')
        inputs['assets/audio-bed.wav'] = bed_path
    check = verify_sources(root, item)
    if check['status'] != 'verified':
        raise ValueError('先安装/核对该方法的固定来源；现有修改不会覆盖：' + check['status'])
    project.mkdir(parents=True, exist_ok=False)
    (project / 'assets').mkdir()
    for name, original in inputs.items():
        shutil.copyfile(original, project / name)
    spec['scene_html'] = 'scene-template.html'
    spec['assets'] = {key: 'assets/' + key + Path(value).suffix.lower() for key, value in spec['assets'].items()}
    if spec.get('audio_bed'):
        spec['audio_bed']['path'] = 'assets/audio-bed.wav'
    write(project / 'spec.json', spec)
    frozen = {name: digest(project / name) for name in [*inputs, 'spec.json']}
    state = {'schema': 1, 'phase': 'prepared', 'base_url': base, 'root': str(root.resolve()),
             'recipe': item['id'], 'source_ref': item['ref'], 'source_url': item['upstream_url'],
             'article': catalog()['article'], 'inputs': frozen, 'receipts': {}, 'downloads': {},
             'quality_review': 'pending', 'listening_review': 'pending'}
    write(project / 'production.json', state)
    return state


def dispatch(client, project, state, name, route, payload):
    if name in state['receipts']:
        return state['receipts'][name]
    if state.get('dispatching'):
        raise ValueError('上次提交结果不明：' + state['dispatching'] + '；请先核对工作台任务，不能自动重复提交')
    state['dispatching'] = name
    write(project / 'production.json', state)
    result = client.json(route, payload)
    state['receipts'][name] = result
    state.pop('dispatching', None)
    write(project / 'production.json', state)
    return result


def reuse_speech(previous, project, state):
    """A visual revision can reuse only the exact original narration and voice."""
    old = load_payload(previous / 'production.json')
    old_spec = validate(load_payload(previous / 'spec.json'))
    spec = validate(load_payload(project / 'spec.json'))
    if (old['root'] != state['root'] or old['base_url'] != state['base_url']
            or old_spec['speech'] != spec['speech']
            or ''.join(x['narration'] for x in old_spec['scenes']) != ''.join(x['narration'] for x in spec['scenes'])):
        raise ValueError('复用配音要求相同工作台、逐字原稿和音色/语速')
    if 'speech' not in old['receipts'] or any(name not in old['downloads'] for name in ('narration.wav', 'alignment.json')):
        raise ValueError('旧工程还没有完整配音及时间戳')
    for name in ('spec.json', 'narration.wav', 'alignment.json'):
        expected = old['inputs'][name] if name == 'spec.json' else old['downloads'][name]['sha256']
        if digest(previous / name) != expected:
            raise ValueError('旧工程的原稿或音频已修改，不能自动复用：' + name)
    for name in ('narration.wav', 'alignment.json'):
        with (project / name).open('xb') as target, (previous / name).open('rb') as source:
            shutil.copyfileobj(source, target)
        state['downloads'][name] = {**old['downloads'][name], 'file': str((project / name).resolve())}
    state['receipts']['speech'] = old['receipts']['speech']
    state['reused_speech_from'] = str(previous.resolve())
    write(project / 'production.json', state)


def await_job(client, identity, deadline):
    while True:
        result = client.job(identity)
        if result.get('status') == 'done': return result
        if result.get('status') in {'error', 'failed', 'cancelled'}:
            raise ValueError('任务失败，保留原工程：' + str(result.get('error', identity)))
        if time.monotonic() >= deadline: return None
        time.sleep(2)


def download(client, project, state, field, route):
    if field in state['downloads']:
        if digest(project / field) != state['downloads'][field]['sha256']:
            raise ValueError('已下载文件被修改，保留修改并停止：' + field)
        return
    target = project / field
    if target.exists():
        raise ValueError('文件存在但缺少下载收据，先核对后再继续：' + field)
    state['downloads'][field] = save_download(client, route, target, 200_000_000)
    write(project / 'production.json', state)


def mix_audio(project, state, spec, seconds):
    """Keep the exact voice master; pad/mix a separately credited optional bed."""
    voice = project / 'narration.wav'
    if not spec.get('audio_bed'):
        return voice
    name = 'soundtrack.wav'
    target = project / name
    outputs = state.setdefault('outputs', {})
    if name in outputs:
        if digest(target) != outputs[name]:
            raise ValueError('混音已修改，未覆盖')
        return target
    if target.exists():
        raise ValueError('混音存在但缺少收据，未覆盖')
    bed = spec['audio_bed']
    temporary = project / ('.mix-' + uuid.uuid4().hex + '.wav')
    command = [str(Path(state['root']) / 'tools/ffmpeg.exe'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
               '-i', str(voice)]
    if bed.get('loop'):
        command += ['-stream_loop', '-1']
    command += ['-i', str(source_path(project, bed['path']))]
    graph = (f'[0:a]apad,atrim=duration={seconds},asetpts=PTS-STARTPTS[v];'
             f'[1:a]volume={bed["gain"]},apad,atrim=duration={seconds},asetpts=PTS-STARTPTS,'
             f'afade=t=in:d=0.15,afade=t=out:st={max(0, seconds-.45)}:d=0.45[b];'
             '[v][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]')
    command += ['-filter_complex', graph, '-map', '[a]', '-t', str(seconds), '-ar', '48000', '-ac', '2',
                '-c:a', 'pcm_s16le', str(temporary)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=60,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('背景音混合失败：' + result.stderr.decode('utf-8', errors='replace')[-1200:])
        with wave.open(str(temporary), 'rb') as mixed:
            if abs(mixed.getnframes() / mixed.getframerate() - seconds) > .01:
                raise ValueError('混音长度与时间轴不符')
        with target.open('xb') as output_file, temporary.open('rb') as input_file:
            shutil.copyfileobj(input_file, output_file)
    finally:
        temporary.unlink(missing_ok=True)
    outputs[name] = digest(target)
    state['audio_mix'] = {'voice': 'narration.wav', 'bed': bed, 'duration': seconds, 'file': name,
                          'limiter_peak': .95, 'subjective_listening': 'pending'}
    write(project / 'production.json', state)
    return target


def deliver(client, project, state, timeline, plan, rendered):
    """Export our own new job's files; update shots through the revisioned API."""
    outputs = state.setdefault('outputs', {})
    root = Path(state['root'])
    clips = project / 'scenes'; clips.mkdir(exist_ok=True)
    for index, scene in enumerate(timeline['scenes']):
        name = 'scenes/' + scene['id'] + '.mp4'
        target = source_path(project, name)
        if name in outputs:
            if digest(target) != outputs[name]:
                raise ValueError('镜头文件已修改，未覆盖：' + name)
            continue
        if target.exists():
            raise ValueError('镜头文件已存在但没有导出收据，未覆盖：' + name)
        seconds = (timeline['duration'] if index == len(timeline['scenes']) - 1 else scene['end']) - scene['start']
        temporary = clips / ('.' + uuid.uuid4().hex + '.mp4')
        try:
            completed = subprocess.run([str(root / 'tools/ffmpeg.exe'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                '-ss', str(scene['start']), '-i', str(project / 'video.mp4'), '-t', str(seconds),
                '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19',
                '-c:a', 'aac', '-movflags', '+faststart', str(temporary)], capture_output=True, timeout=120,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if completed.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                raise ValueError('镜头导出失败：' + completed.stderr.decode('utf-8', errors='replace')[-1200:])
            with target.open('xb') as output_file, temporary.open('rb') as input_file:
                shutil.copyfileobj(input_file, output_file)
        finally:
            temporary.unlink(missing_ok=True)
        outputs[name] = digest(target)
        write(project / 'production.json', state)
    if 'attach' not in state['receipts'] and not state.get('plan_attachment'):
        current = client.json('/api/generation/plan?id=' + plan['id'])
        if current['revision'] != plan['revision']:
            state['plan_attachment'] = 'newer_edit_preserved'
        else:
            for row in current['shots']:
                row.update(asset_path=str((project / 'scenes' / (row['id'] + '.mp4')).resolve()), status='generated')
            saved = dispatch(client, project, state, 'attach', '/api/generation/plan', current)
            state.update(plan_attachment='generated_shots_attached', plan_revision=saved['revision'])
        write(project / 'production.json', state)
    bundle = project / 'delivery.zip'
    if 'delivery.zip' not in outputs:
        manifest = {'title': plan['title'], 'method': state['recipe'], 'source_ref': state['source_ref'],
                    'duration': rendered['duration'], 'width': rendered['width'], 'height': rendered['height'],
                    'fps': rendered['fps'], 'video_sha256': digest(project / 'video.mp4'),
                    'quality_review': 'pending', 'motion': 'authored deterministic 2D animation',
                    'audio_mix': state.get('audio_mix'), 'voice_master_sha256': digest(project / 'narration.wav'),
                    'timing': timeline['timing']}
        write(project / 'delivery-manifest.json', manifest)
        names = [*state['inputs'], 'video.mp4', 'narration.wav', 'alignment.json', 'timeline.json',
                 'subtitles.srt', 'scene.html', 'render-qa.json', 'delivery-manifest.json', *outputs]
        with zipfile.ZipFile(bundle, 'x', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(source_path(project, name), name)
        outputs['delivery.zip'] = digest(bundle)
        write(project / 'production.json', state)
    elif digest(bundle) != outputs['delivery.zip']:
        raise ValueError('交付包已修改，未覆盖')
    identity = rendered['job_id']
    if not re.fullmatch(r'generation-[a-f0-9]{10}', identity):
        raise ValueError('交付任务 ID 无效')
    job_dir = source_path(root / 'projects/studio', identity)
    # Only enrich the exact successful job returned by our render receipt.
    if digest(job_dir / 'video.mp4') != state['downloads']['video.mp4']['sha256']:
        raise ValueError('工作台任务与本次视频不一致，未附加交付文件')
    for name in ('subtitles.srt', 'timeline.json', 'delivery.zip'):
        destination = source_path(job_dir, name)
        if destination.exists():
            if digest(destination) != digest(project / name):
                raise ValueError('工作台已有同名交付文件，未覆盖：' + name)
        else:
            with destination.open('xb') as target, (project / name).open('rb') as source:
                shutil.copyfileobj(source, target)
    state['library_id'] = 'lib-' + hashlib.sha256(('project:' + identity).encode()).hexdigest()[:24]
    state['library_url'] = client.base + '/library?item=' + state['library_id']
    state['bundle'] = str(bundle.resolve())


def advance(client, project, state, wait):
    spec = validate(load_payload(project / 'spec.json'))
    for name, expected in state['inputs'].items():
        if digest(source_path(project, name)) != expected:
            raise ValueError('制作快照已修改；请另建版本，不能续作时更换原稿：' + name)
    deadline = time.monotonic() + wait
    speech = dispatch(client, project, state, 'speech', '/api/speech',
                      {**spec['speech'], 'text': ''.join(s['narration'] for s in spec['scenes']), 'subtitles': True})
    state['phase'] = 'speech'; write(project / 'production.json', state)
    spoken = await_job(client, speech['job_id'], deadline)
    if spoken is None: return state
    for field, key in [('narration.wav', 'audio'), ('alignment.json', 'alignment')]:
        download(client, project, state, field, spoken[key])
    with wave.open(str(project / 'narration.wav'), 'rb') as audio:
        seconds = audio.getnframes() / audio.getframerate()
    words = json.loads((project / 'alignment.json').read_text(encoding='utf-8'))
    timeline = build_timeline(spec['scenes'], words, seconds, spec['fps'], spec['tail'])
    audio_path = mix_audio(project, state, spec, timeline['duration'])
    write(project / 'timeline.json', timeline)
    (project / 'subtitles.srt').write_text('\n'.join(f'{i}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"].strip()}\n'
                                                  for i, c in enumerate(timeline['captions'], 1)), encoding='utf-8')
    assets = {key: (Path(path).suffix, (project / path).read_bytes()) for key, path in spec['assets'].items()}
    compiled = compose_html((project / 'scene-template.html').read_text(encoding='utf-8'), timeline, spec, assets,
                            (project / 'creative-canvas.js').read_text(encoding='utf-8'))
    import code_animation
    payload = {'html': compiled, **{key: spec[key] for key in ('width', 'height', 'fps')},
               'duration': timeline['duration'], 'audio_path': str(audio_path.resolve())}
    code_animation.normalize(payload)
    if len(json.dumps(payload, ensure_ascii=False).encode()) + 1000 > REQUEST_LIMIT:
        raise ValueError('图像和动画源码超过 API 请求上限；请保留原片并另建较小的素材版本')
    (project / 'scene.html').write_text(compiled, encoding='utf-8')
    plan_result = dispatch(client, project, state, 'plan', '/api/generation/plan', plan_request(spec, timeline, state['recipe']))
    plan = plan_result.get('plan', plan_result)
    render = dispatch(client, project, state, 'render', '/api/generation/render',
                      {'plan_id': plan['id'], 'kind': 'code-animation', 'preview': False, 'payload': payload})
    state.update(phase='render', plan_id=plan['id']); write(project / 'production.json', state)
    rendered = await_job(client, render['job_id'], deadline)
    if rendered is None: return state
    for field, key in [('video.mp4', 'video'), ('render-qa.json', 'qa')]:
        download(client, project, state, field, rendered[key])
    qa = load_payload(project / 'render-qa.json')
    if not qa.get('checks', {}).get('decoded') or not qa['checks'].get('audio_stream_decoded'):
        raise ValueError('渲染器未提供完整音画解码证据')
    if abs(rendered['duration'] - timeline['duration']) > 1 / spec['fps']:
        raise ValueError('实际片长与音频驱动时间轴不一致')
    state['phase'] = 'delivery'; write(project / 'production.json', state)
    deliver(client, project, state, timeline, plan, rendered)
    state.update(phase='done', job_id=render['job_id'], duration=rendered['duration'],
                 speech=spoken.get('speech', {}), video=str((project / 'video.mp4').resolve()),
                 plan_url=client.base + '/generation?plan=' + plan['id'],
                 rendered_motion='authored deterministic 2D animation; not model-generated I2V')
    state.pop('last_error', None)
    write(project / 'production.json', state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--url', default=os.environ.get('AI_VIDEO_STUDIO_URL', 'http://127.0.0.1:8189'))
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('produce')
    create.add_argument('--recipe', required=True)
    create.add_argument('--spec', type=Path, required=True)
    create.add_argument('--out', type=Path, required=True)
    create.add_argument('--reuse-speech', type=Path, help='Reuse verified audio for an unchanged script and voice')
    create.add_argument('--wait', type=float, default=60)
    resume = commands.add_parser('resume')
    resume.add_argument('--project', type=Path, required=True)
    resume.add_argument('--wait', type=float, default=60)
    status = commands.add_parser('status')
    status.add_argument('--project', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'status':
        output(load_payload(args.project / 'production.json')); return 0
    finite(args.wait, 'wait', 0, 3600)
    root = args.root or find_root()
    if root is None:
        raise ValueError('未找到工作台，请传入 --root')
    root = root.resolve()
    sys.path.insert(0, str(root / 'scripts'))
    client = Client(args.url)
    from studio_client import doctor
    health = doctor(client)
    if not health.get('service_available') or Path(health.get('root', '')).resolve() != root:
        raise ValueError('当前服务与工作台根目录不一致，请先运行 doctor')
    project = (args.out if args.command == 'produce' else args.project).resolve()
    if args.command == 'produce':
        state = prepare(root, recipe(args.recipe), args.spec, project, client.base)
        if args.reuse_speech:
            reuse_speech(args.reuse_speech.resolve(), project, state)
    else:
        state = load_payload(project / 'production.json')
        if state['base_url'] != client.base or Path(state['root']).resolve() != root:
            raise ValueError('续作必须使用原工作台和服务地址')
    with locked(project):
        state = load_payload(project / 'production.json')
        try:
            result = advance(client, project, state, args.wait)
        except Exception as exc:
            state['last_error'] = str(exc)
            write(project / 'production.json', state)
            raise
    output({key: result.get(key) for key in ('phase', 'recipe', 'job_id', 'plan_id', 'duration', 'video', 'plan_url', 'library_url', 'bundle', 'quality_review')})
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, StudioError) as exc:
        output({'error': str(exc), 'detail': getattr(exc, 'detail', None)}, stream=sys.stderr)
        raise SystemExit(1)

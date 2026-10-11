"""Web production of the reviewed local creative-method editions.

Uses the same speech/timeline/renderer as the CLI, inside an isolated worker.
Inputs are frozen before queueing; a retry never changes the selected artwork.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave
import zipfile

from prompt_library import ROOT
import generation_plans as plans

SKILL = ROOT/'skills/ai-video-studio/scripts'
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))
import creative_film as film
import creative_video
import sync_creative_methods


def definition(identity):
    rows = creative_video.catalog()['skills']
    item = next((row for row in rows if row['id'] == identity), None)
    production = json.loads((ROOT/'skills/ai-video-studio/references/creative-production-catalog.json').read_text('utf-8'))
    entry = next((row for row in production['methods'] if row['id'] == identity), None)
    if not item or not entry or entry['executor'] != 'creative_film.py':
        raise ValueError('请选择已接入的本地视频方法；白板请进入白板编辑器')
    path = ROOT/entry['example']
    return item, entry, path, film.validate(json.loads(path.read_text('utf-8')))


def asset_packs(identity, spec):
    """Only previously registered, hash-checked inputs of this exact method."""
    if not spec['assets'] and not spec.get('audio_bed'):
        return []
    packs = []
    for record in (ROOT/'projects/creative-films').glob('*/production.json'):
        try:
            base = plans._plain(record.parent)
            state = json.loads(record.read_text('utf-8'))
            if state.get('recipe') != identity:
                continue
            original = json.loads((base/'spec.json').read_text('utf-8'))
            names = dict(original['assets'])
            if spec.get('audio_bed'):
                names['audio-bed'] = original['audio_bed']['path']
            if set(names) != set(spec['assets']) | ({'audio-bed'} if spec.get('audio_bed') else set()):
                continue
            paths = {key: creative_video.source_path(base, value) for key, value in names.items()}
            if any(film.digest(path) != state['inputs'].get(names[key]) for key, path in paths.items()):
                continue
            packs.append({'id': base.name, 'label': original['title']+' · '+base.name,
                          'paths': paths, 'modified': record.stat().st_mtime})
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return sorted(packs, key=lambda row: row['modified'], reverse=True)


def readiness():
    rows = []
    for method in sync_creative_methods.catalog():
        if method['route'] == 'whiteboard':
            continue
        _, _, _, spec = definition(method['id'])
        packs = asset_packs(method['id'], spec)
        needs = bool(spec['assets'] or spec.get('audio_bed'))
        rows.append({'id': method['id'], 'ready': not needs or bool(packs),
                     'message': '复用已保留的本方法画面与背景音，重新制作配音和视频。' if needs and packs else
                                '无需外部画面素材，使用本方法的二维场景。' if not needs else
                                '尚无已登记的本方法素材，请先通过 creative_film 制作并保留素材工程。',
                     'packs': [{'id': row['id'], 'label': row['label']} for row in packs]})
    return rows


def publish_primary(dest):
    """Expose the shared project contract for library, editing and export tools."""
    qa = json.loads((dest/'rendered/qa.json').read_text('utf-8'))
    if film.digest(dest/'rendered/video.mp4') != qa['video_sha256']:
        raise ValueError('成片校验不符，未发布给其他创作工具')
    for name in ('video.mp4', 'cover.png', 'qa.json', 'scene.html'):
        source, target = dest/'rendered'/name, dest/name
        if target.exists():
            if film.digest(target) != film.digest(source):
                raise ValueError('工程已有不同版本的交付文件，未覆盖：'+name)
        else:
            with target.open('xb') as output, source.open('rb') as original:
                shutil.copyfileobj(original, output)


def freeze(identity, plan, pack_id, dest):
    item, entry, example, spec = definition(identity)
    method = next(row for row in sync_creative_methods.catalog() if row['id'] == identity)
    if f'[{identity}]' not in plan['brief'] or plan['route'] != method['route']:
        raise ValueError('当前计划尚未载入此方法，请先用方法示例新建计划')
    expected_style = '\n'.join(filter(None, [method['example']['style'], method['guidance']]))
    if plan.get('style', '') != expected_style or plan.get('character', '') != method['example']['character']:
        raise ValueError('风格或角色约定已修改，请关闭方法场景模式，使用通用创作设计新画面')
    if plan['speech_backend'] != 'windows' or plan.get('voice_id') or any(s.get('voice_id') for s in plan['shots']):
        raise ValueError('本方法的本地示例使用 Windows 配音；不会替换已选择的模型音色')
    if len(plan['shots']) != len(spec['scenes']):
        raise ValueError('本地示例需保持镜头数量和顺序。新增画面请使用通用创作或修改方法场景')
    for shot, scene in zip(plan['shots'], spec['scenes']):
        if any(shot.get(key, '') != scene.get(key, '') for key in ('visual', 'action', 'camera')):
            raise ValueError('画面描述已修改。本地示例不能把新描述自动变成画面，请使用通用创作或修改方法场景')
        scene['narration'] = shot['narration']
    spec['title'] = plan['title']
    spec = film.validate(spec)
    checked = creative_video.verify_sources(ROOT, item)
    if checked['status'] != 'verified':
        raise ValueError('方法来源核对未通过：'+checked['status'])
    import lightweight_speech
    spec['speech']['voice_id'] = lightweight_speech.validate('windows', spec['speech'].get('voice_id', ''), spec['speech']['speed'])
    files = {'scene-template.html': example.parent/spec['scene_html'], 'creative-canvas.js': SKILL/'creative-canvas.js'}
    if spec['assets'] or spec.get('audio_bed'):
        packs = asset_packs(identity, spec)
        pack = next((row for row in packs if row['id'] == pack_id), None)
        if not pack:
            raise ValueError('所选素材工程缺失或已修改，请刷新后重新选择')
        for key in spec['assets']:
            source = pack['paths'][key]
            spec['assets'][key] = 'assets/'+key+source.suffix
            files[spec['assets'][key]] = source
        if spec.get('audio_bed'):
            spec['audio_bed']['path'] = 'assets/audio-bed.wav'
            files['assets/audio-bed.wav'] = pack['paths']['audio-bed']
    spec['scene_html'] = 'scene-template.html'
    inputs = dest/'method-inputs'; inputs.mkdir()
    for name, source in files.items():
        target = inputs/name; target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(source, target)
    film.write(inputs/'spec.json', spec)
    snapshot = {'id': identity, 'source_ref': item['ref'], 'source_url': item['upstream_url'],
                'asset_pack': pack_id, 'boundary': entry['boundary'],
                'inputs': {name: film.digest(inputs/name) for name in [*files, 'spec.json']}}
    film.write(dest/'method-snapshot.json', snapshot)
    return snapshot


def run(dest):
    request = json.loads((dest/'render-request.json').read_text('utf-8'))
    snapshot = json.loads((dest/'method-snapshot.json').read_text('utf-8'))
    inputs = dest/'method-inputs'
    for name, expected in snapshot['inputs'].items():
        if film.digest(creative_video.source_path(inputs, name)) != expected:
            raise ValueError('方法制作快照已变化，不能继续覆盖原任务：'+name)
    spec = film.validate(json.loads((inputs/'spec.json').read_text('utf-8')))
    # Work products have receipts separate from immutable inputs and API status.
    state_path = dest/'method-progress.json'
    state = json.loads(state_path.read_text('utf-8')) if state_path.exists() else {'root': str(ROOT), 'outputs': {}}
    def record(name):
        state['outputs'][name] = film.digest(dest/name); film.write(state_path, state)
    def exists(name):
        if name not in state['outputs']:
            if (dest/name).exists():
                raise ValueError('发现未登记的已有产物，请另建版本：'+name)
            return False
        if film.digest(dest/name) != state['outputs'][name]:
            raise ValueError('已有产物已修改，未覆盖：'+name)
        return True
    import lightweight_speech
    if not exists('narration.wav'):
        lightweight_speech.synthesize(''.join(s['narration'] for s in spec['scenes']), dest/'narration.wav',
                                      voice=spec['speech']['voice_id'], speed=spec['speech']['speed'])
        for name in ('narration.wav', 'narration.alignment.json', 'narration.speech.json'):
            record(name)
    else:
        exists('narration.alignment.json'); exists('narration.speech.json')
    seconds = lightweight_speech.duration(dest/'narration.wav')
    words = json.loads((dest/'narration.alignment.json').read_text('utf-8'))
    timeline = film.build_timeline(spec['scenes'], words, seconds, spec['fps'], spec['tail'])
    mix_spec = copy.deepcopy(spec)
    if mix_spec.get('audio_bed'):
        mix_spec['audio_bed']['path'] = 'method-inputs/'+mix_spec['audio_bed']['path']
    audio = film.mix_audio(dest, state, mix_spec, timeline['duration'])
    film.write(state_path, state)
    assets = {key: (Path(name).suffix, (inputs/name).read_bytes()) for key, name in spec['assets'].items()}
    html = film.compose_html((inputs/spec['scene_html']).read_text('utf-8'), timeline, spec, assets,
                             (inputs/'creative-canvas.js').read_text('utf-8'))
    # Preview is the first complete scene, never an unexplained three-second cut.
    duration = timeline['scenes'][0]['end'] if request['preview'] else timeline['duration']
    rendered_dir = dest/'rendered'
    if not exists('rendered/video.mp4'):
        import code_animation
        result = code_animation.render({'html': html, 'audio_path': str(audio), 'duration': duration,
                                        **{k: spec[k] for k in ('width', 'height', 'fps')}}, rendered_dir)
        for name in ('video.mp4', 'cover.png', 'qa.json', 'scene.html'): record('rendered/'+name)
    else:
        for name in ('cover.png', 'qa.json', 'scene.html'): exists('rendered/'+name)
        result = json.loads((rendered_dir/'qa.json').read_text('utf-8'))
    publish_primary(dest)
    for name in ('video.mp4', 'cover.png', 'qa.json', 'scene.html'): record(name)
    film.write(dest/'timeline.json', timeline)
    captions = [dict(c, end=min(c['end'], result['duration'])) for c in timeline['captions'] if c['start'] < result['duration']]
    lightweight_speech.write_srt(dest/'subtitles.srt', captions)
    rows = []
    for index, (scene, shot) in enumerate(zip(timeline['scenes'], request['plan']['shots'])):
        if request['preview'] and index: break
        name = 'scenes/'+shot['id']+'.mp4'
        if not exists(name):
            target = dest/name; target.parent.mkdir(exist_ok=True)
            end = result['duration'] if request['preview'] or index == len(timeline['scenes'])-1 else scene['end']
            subprocess.run([str(ROOT/'tools/ffmpeg.exe'), '-v', 'error', '-nostdin', '-n', '-ss', str(scene['start']),
                            '-i', str(rendered_dir/'video.mp4'), '-t', str(end-scene['start']), '-c:v', 'libx264',
                            '-preset', 'fast', '-crf', '19', '-c:a', 'aac', '-movflags', '+faststart', str(target)],
                           check=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            record(name)
        rows.append({'id': shot['id'], 'path': name})
    manifest = {**snapshot, 'title': spec['title'], 'plan_id': request['plan_id'],
                'plan_revision': request['plan']['revision'], 'video_sha256': film.digest(rendered_dir/'video.mp4'),
                'duration': result['duration'], 'preview': request['preview'], 'quality_review': 'pending',
                'listening_review': 'pending', 'timing': timeline['timing'], 'audio_mix': state.get('audio_mix')}
    film.write(dest/'delivery-manifest.json', manifest)
    if not exists('delivery.zip'):
        names = ['delivery-manifest.json', 'subtitles.srt', 'timeline.json', 'plan.json', 'method-snapshot.json',
                 *[name for name in state['outputs'] if not name.startswith('rendered/')]]
        with zipfile.ZipFile(dest/'delivery.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
            for name in names: archive.write(dest/name, name)
            for name in snapshot['inputs']: archive.write(inputs/name, 'method-inputs/'+name)
        record('delivery.zip')
    return {**{k: result[k] for k in ('width', 'height', 'fps', 'frames', 'duration')},
            'video': 'video.mp4', 'image': 'cover.png', 'qa': 'qa.json',
            'subtitle': 'subtitles.srt', 'bundle': 'delivery.zip', 'shot_outputs': rows}


if __name__ == '__main__':
    directory = Path(sys.argv[1])
    try:
        film.write(directory/'render-result.json', run(directory))
    except Exception as exc:
        film.write(directory/'failure.json', {'error': str(exc)})
        raise

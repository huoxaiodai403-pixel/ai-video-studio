"""Render true Simon/RoughJS pen animation using existing local narration.

No TTS, network request or generated JavaScript is used. The source storyboard is
validated into JSON, then the fixed simon_bridge.cjs builds editable Excalidraw
documents. --stills can run before speech generation; --render requires both the
WAV and its real forced-alignment timestamps for every scene.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'apps/simon-skills/skills/whiteboard-video'
FPS, LEAD, HOLD = 30, 0.3, 0.7
SAMPLE_STICKERS = ('reader', 'stepper', 'stuck', 'panicked')


def readiness():
    """Fast local availability checks for the workbench; does not load AI models."""
    node = ROOT / 'tools/node/node.exe'
    if not node.is_file(): node = shutil.which('node')
    ffmpeg = ROOT / 'tools/ffmpeg.exe'
    if not ffmpeg.is_file(): ffmpeg = shutil.which('ffmpeg')
    checks = [{'name': 'node', 'ready': bool(node), 'message': str(node or '缺少 Node.js')},
              {'name': 'ffmpeg', 'ready': bool(ffmpeg), 'message': str(ffmpeg or '缺少 ffmpeg')},
              {'name': 'simon-source', 'ready': (SKILL / 'lib/render.js').is_file(), 'message': str(SKILL)}]
    env = os.environ.copy(); env['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'cache/ms-playwright')
    if node and (SKILL / 'package.json').is_file():
        try:
            probe = subprocess.run([str(node), '-e', "const fs=require('fs');require('roughjs');require('lz-string');const p=require('playwright').chromium.executablePath();console.log(JSON.stringify({path:p,ready:fs.existsSync(p)}))"],
                                   cwd=str(SKILL), env=env, capture_output=True, text=True, timeout=15, check=True)
            browser = json.loads(probe.stdout)
            checks.extend([{'name': 'node-packages', 'ready': True, 'message': 'Playwright / RoughJS / lz-string'},
                           {'name': 'chromium', 'ready': browser['ready'], 'message': browser['path']}])
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            checks.append({'name': 'node-packages', 'ready': False, 'message': f'请安装白板 Node 依赖及 Chromium: {error}'})
    else:
        checks.append({'name': 'node-packages', 'ready': False, 'message': '需要 Node.js 与 Simon 项目'})
    return {'ready': all(item['ready'] for item in checks), 'checks': checks}


def _read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def _norm(value):
    return ''.join(c for c in value if c.isalnum()).lower()


def _beats(scene, target):
    text = scene['narration'].strip()
    explicit = scene.get('board_beats')
    if explicit is not None:
        if not isinstance(explicit, list) or not 1 <= len(explicit) <= 3 or any(not isinstance(b, str) or not _norm(b) for b in explicit):
            raise ValueError(f"{scene['id']}: board_beats 必须包含 1–3 段旁白")
        if _norm(''.join(explicit)) != _norm(text):
            raise ValueError(f"{scene['id']}: board_beats 必须按顺序完整覆盖 narration，不能改写或遗漏")
        # Keep punctuation from the original script, not from supplied beat fragments.
        lengths = [len(_norm(b)) for b in explicit]
        output, cursor = [], 0
        for i, count in enumerate(lengths):
            end, seen = cursor, 0
            while end < len(text) and seen < count:
                seen += int(text[end].isalnum()); end += 1
            while end < len(text) and not text[end].isalnum(): end += 1
            if i == len(lengths) - 1: end = len(text)
            output.append(text[cursor:end].strip()); cursor = end
        return output
    clauses = [x.strip() for x in re.findall(r'[^。！？!?；;]+[。！？!?；;]*', text) if _norm(x)]
    if len(clauses) <= target:
        return clauses or [text]
    output, cursor = [], 0
    for index in range(target):
        remaining = target - index
        take = max(1, math.ceil((len(clauses) - cursor) / remaining))
        output.append(''.join(clauses[cursor:cursor + take])); cursor += take
    return output


def _validate(spec):
    if spec.get('render_mode') != 'excalidraw':
        raise ValueError("此渲染器要求 storyboard.json 的 render_mode='excalidraw'")
    source = spec.get('scenes')
    if not isinstance(source, list) or not 1 <= len(source) <= 40:
        raise ValueError('需要 1–40 个白板场景')
    scenes, ids = [], set()
    for scene in source:
        sid = scene.get('id', '')
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', sid) or sid in ids:
            raise ValueError('场景 id 必须唯一且只含英文字母、数字、下划线、连字符')
        ids.add(sid)
        narration = scene.get('narration')
        if not isinstance(narration, str) or not _norm(narration) or '|' in narration:
            raise ValueError(f'{sid}: narration 不能为空，也不能包含 beat 分隔符 |')
        title = scene.get('board_title')
        cards = scene.get('board_cards')
        if not isinstance(title, str) or not title.strip() or len(title) > 70:
            raise ValueError(f'{sid}: board_title 需要 1–70 字')
        if not isinstance(cards, list) or not 1 <= len(cards) <= 3 or any(not isinstance(c, str) or not c.strip() or len(c) > 120 for c in cards):
            raise ValueError(f'{sid}: board_cards 需要 1–3 个短句，每项最多 120 字')
        layout = scene.get('board_layout', 'steps')
        if layout not in ('opening', 'compare', 'steps', 'summary'):
            raise ValueError(f'{sid}: 不支持的 board_layout: {layout}')
        stickers = scene.get('board_stickers', [])
        if not isinstance(stickers, list) or len(stickers) > len(cards) or any(s and (not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', s)) for s in stickers):
            raise ValueError(f'{sid}: board_stickers 只能引用 assets 中已有 PNG 的安全文件名')
        sample = scene.get('board_sticker', 'none')
        if sample not in (*SAMPLE_STICKERS, 'none', '', None):
            raise ValueError(f'{sid}: board_sticker 必须是 reader / stepper / stuck / panicked / none')
        stickers = list(stickers)
        if sample and sample != 'none':
            if not stickers: stickers = ['simon-' + sample]
            elif not stickers[0]: stickers[0] = 'simon-' + sample
        scenes.append({'id': sid, 'title': title.strip(), 'layout': layout, 'cards': [c.strip() for c in cards],
                       'beats': _beats(scene, len(cards)), 'stickers': stickers,
                       'sticker': 'simon-' + sample if sample and sample != 'none' else None})
    return scenes


def _audio_info(project, scene):
    sid = scene['id']
    wav = project / 'audio' / f'{sid}.wav'
    alignment = project / 'audio' / f'{sid}.alignment.json'
    if not wav.is_file() or not alignment.is_file():
        raise FileNotFoundError(f'{sid}: 缺少本地配音或真实时间对齐；请先运行配音和对齐：{wav} / {alignment}')
    with wave.open(str(wav), 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
    if duration <= 0:
        raise ValueError(f'{sid}: 配音时长必须大于零')
    raw = _read(alignment)
    if not isinstance(raw, list) or not raw:
        raise ValueError(f'{sid}: alignment.json 没有逐字/逐词时间戳')
    words, previous, position = [], 0.0, 0
    for item in raw:
        text = item.get('text')
        if not isinstance(text, str): raise ValueError(f'{sid}: 无效的对齐文字')
        start, end = float(item['start']), float(item['end'])
        if not all(math.isfinite(t) for t in (start, end)) or start < -0.05 or start > duration or end < start or start + 0.05 < previous or end > duration + 0.25:
            raise ValueError(f'{sid}: 无效或越界的配音时间戳 {start}–{end} / {duration}')
        previous = start
        count = len(_norm(text))
        if count:
            words.append({'w': text, 's': min(duration, max(0.0, start)), 'e': min(duration, max(0.0, end)), 'p': position, 'n': count})
            position += count
    if _norm(''.join(w['w'] for w in words)) != _norm(''.join(scene['beats'])):
        raise ValueError(f'{sid}: 对齐文本与当前旁白不一致，请重新运行语音对齐，不能用旧音轨估算')
    starts, cursor = [], 0
    for beat in scene['beats']:
        word = next(w for w in words if w['p'] + w['n'] > cursor)
        starts.append(word['s'] + (word['e'] - word['s']) * (cursor - word['p']) / word['n'])
        cursor += len(_norm(beat))
    return {'name': sid, 'duration': duration, 'segments': scene['beats'], 'segmentStarts': starts,
            'wordList': [{k: w[k] for k in ('w', 's', 'e')} for w in words],
            'alignmentSource': str(alignment), 'estimated': False}


def _run(command, env, cwd):
    print('Whiteboard:', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), env=env, cwd=str(cwd), check=True)


def render(project, stills=False):
    project = Path(project).resolve()
    spec = _read(project / 'storyboard.json')
    scenes = _validate(spec)
    if not (SKILL / 'lib/render.js').is_file():
        raise FileNotFoundError(f'尚未拉取 Simon whiteboard-video：{SKILL}')
    node = ROOT / 'tools/node/node.exe'
    if not node.is_file():
        node = shutil.which('node')
    if not node: raise RuntimeError('缺少 Node.js，请安装 Node.js 20.12 或以上版本')
    ffmpeg = ROOT / 'tools/ffmpeg.exe'
    if not ffmpeg.is_file(): ffmpeg = shutil.which('ffmpeg')
    if not stills and not ffmpeg: raise RuntimeError('缺少 ffmpeg，无法编码白板视频')
    config = _read(SKILL / 'config.json')
    config['dirs'].update({'projects': str(project.parent), 'build': str(project / 'whiteboard'), 'studio': str(project / 'whiteboard')})
    config['render'].update({'fps': FPS, 'leadSeconds': LEAD, 'holdSeconds': HOLD, 'workers': 2})
    config['brand'].update({'name': '白板实验室', 'slogan': '', 'logo': ''})
    config['brand']['endCard']['enabled'] = False
    config['cover']['seriesTag'] = '白板讲解'
    config['tts']['speed'] = 1  # Only used to estimate pre-audio stills, never synthesizes speech.
    _write(project / 'simon-config.json', config)
    assets = project / 'assets'; assets.mkdir(exist_ok=True)
    requested = {'simon-reader'} | {s['sticker'] for s in scenes if s['sticker']}
    for name in requested:
        source = next((SKILL / 'examples').glob(f'*/assets/{name.removeprefix("simon-")}.png'), None)
        if not source: raise FileNotFoundError(f'缺少上游 MIT 示例贴纸：{name}')
        destination = assets / f'{name}.png'
        if not destination.exists(): shutil.copy2(source, destination)
    _write(project / 'simon-scenes.json', {'scenes': scenes, 'cover_title': scenes[0]['title'], 'cover_sticker': 'simon-reader'})
    # This wrapper contains only a trusted local bridge path. User prose remains JSON.
    bridge_path = json.dumps(str(ROOT / 'scripts/simon_bridge.cjs'))
    (project / 'scenes.js').write_text("'use strict';\n// Edit storyboard.json; this fixed bridge reads simon-scenes.json.\nrequire(" + bridge_path + ").build(__dirname);\n", encoding='utf-8')
    work = project / 'whiteboard/work'
    env = os.environ.copy()
    env['SIMON_WB_CONFIG'] = str(project / 'simon-config.json')
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'cache/ms-playwright')
    if ffmpeg: env['SIMON_FFMPEG'] = str(ffmpeg)
    infos = []
    for scene in scenes:
        audio_target = work / 'audio' / f"{scene['id']}.json"
        if stills:
            # Do not let an older render's timestamps influence a changed storyboard.
            if audio_target.exists(): audio_target.unlink()
            continue
        info = _audio_info(project, scene)
        infos.append(info)
        _write(audio_target, info)
        shutil.copy2(project / 'audio' / f"{scene['id']}.wav", work / 'audio' / f"{scene['id']}.wav")
    _run([node, project / 'scenes.js'], env, project)
    _run([node, SKILL / 'lib/render.js', project, '--stills'], env, project)
    _run([node, SKILL / 'lib/render.js', project, '--cover'], env, project)
    manifest = {'renderer': 'simon-skills/whiteboard-video + RoughJS', 'mode': 'stills' if stills else 'render',
                'native_width': 1920, 'native_height': 1080, 'fps': FPS, 'upscaled': False,
                'preview_frames': [f"whiteboard/work/frames/{s['id']}-{suffix}.png" for s in scenes
                                   for suffix in [*(f'beat{i + 1}' for i in range(len(s['beats']))), 'mid']],
                'covers': ['封面-4x3.png', '封面-3x4.png'],
                'editable_scenes': [f"scenes/{s['id']}.excalidraw.md" for s in scenes],
                'source': 'storyboard.json', 'bridge_source': 'scenes.js', 'audio_alignment': 'real' if not stills else 'estimated-preview-only'}
    if not stills:
        manifest['timing_method'] = '真实逐字或逐词对齐时间戳驱动；beat 边界落在多字词内部时，仅在该词实测起止范围内插值'
    if not stills:
        _run([node, SKILL / 'lib/render.js', project], env, project)
        pending_video = project / 'video.whiteboard-pending.mp4'
        _run([ffmpeg, '-y', '-v', 'error', '-i', work / 'out/master.mp4', '-copyts', '-c', 'copy', '-movflags', '+faststart', pending_video], env, project)
        pending_video.replace(project / 'video.mp4')
        shutil.copy2(project / '字幕.srt', project / 'subtitles.srt')
        timeline, offset = [], 0.0
        for scene, info in zip(scenes, infos):
            total = math.ceil((info['duration'] + LEAD + HOLD) * FPS) / FPS
            timeline.append({'id': scene['id'], 'start': offset, 'duration': total,
                             'audio_start': offset + LEAD, 'audio_duration': info['duration'],
                             'beat_starts': [offset + LEAD + t for t in info['segmentStarts']]})
            offset += total
        _write(project / 'timeline.json', timeline)
        manifest.update({'video': 'video.mp4', 'subtitles': 'subtitles.srt', 'duration': offset,
                         'visual_qa': 'pending-human-review', 'audio_qa': 'pending-human-listening'})
    _write(project / 'whiteboard.manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stills', action='store_true', help='只生成各 beat 预览与两种比例封面，不需要配音')
    mode.add_argument('--render', action='store_true', help='完整渲染（默认），使用已有本地 WAV 和真实对齐时间戳')
    args = parser.parse_args()
    try:
        render(args.project, stills=args.stills)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Simon whiteboard failed: {error}', file=sys.stderr, flush=True)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()

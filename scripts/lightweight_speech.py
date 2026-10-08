"""CPU speech and synthesis timestamps; no torch, GPU, or fabricated ASR."""
import asyncio
import functools
import html
import importlib.util
import json
import math
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from prompt_library import ROOT

EDGE_VOICES = [
    {'id': 'zh-CN-XiaoxiaoNeural', 'label': '晓晓 · 普通话女声'},
    {'id': 'zh-CN-YunxiNeural', 'label': '云希 · 普通话男声'},
    {'id': 'zh-CN-XiaoyiNeural', 'label': '晓伊 · 普通话女声'},
    {'id': 'zh-CN-YunjianNeural', 'label': '云健 · 普通话男声'},
    {'id': 'en-US-JennyNeural', 'label': 'Jenny · 英语女声'},
]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def norm(text):
    return ''.join(c.lower() for c in text if c.isalnum())


def powershell(*args):
    shell = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(ROOT/'scripts/windows_speech.ps1'), *map(str, args)],
                            capture_output=True, encoding='utf-8-sig', errors='replace', timeout=180,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Windows 配音失败，请检查是否已安装所选语言的语音包。' + result.stderr[-700:])
    return json.loads(result.stdout)


@functools.lru_cache(maxsize=1)
def _windows_voices(time_bucket):
    if os.name != 'nt':
        return []
    return powershell('-Action', 'voices')


def windows_voices():
    return _windows_voices(int(time.monotonic() // 60))


def options():
    error = None
    try:
        voices = windows_voices()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        voices, error = [], str(exc)
    default = next((v['id'] for v in voices if v['language'] == 'zh-CN'), voices[0]['id'] if voices else '')
    return {'default_backend': 'windows', 'windows': {'available': bool(voices), 'voices': voices,
            'default_voice': default, 'error': error},
            'edge': {'available': importlib.util.find_spec('edge_tts') is not None, 'voices': EDGE_VOICES,
                     'default_voice': EDGE_VOICES[0]['id'], 'requires_network': True,
                     'note': '通过社区 edge-tts 使用微软在线语音，需要联网，无需 API Key；可用性以试听为准。'}}


def validate(backend, voice='', speed=1.0):
    if backend not in ('windows', 'edge', 'volc', 'online'):
        raise ValueError('请选择 Windows 离线语音、Edge 在线语音或已配置的语音 API。')
    if not isinstance(voice, str) or len(voice) > 200:
        raise ValueError('音色名称格式不正确。')
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2:
        raise ValueError('语速应在 0.5–2 范围内。')
    if backend == 'windows':
        available = options()['windows']
        voice = voice or available['default_voice']
        if not available['available']:
            raise ValueError('没有可用的 Windows 语音。请在 Windows 语言设置中安装语音包，或选择 Edge 在线语音。')
        if voice not in {v['id'] for v in available['voices']}:
            raise ValueError('该 Windows 音色未安装，请重新选择已有音色。')
    elif backend == 'edge':
        if importlib.util.find_spec('edge_tts') is None:
            raise ValueError('Edge 配音依赖未安装，请重新运行 Install-Studio.ps1；也可直接使用 Windows 离线语音。')
        voice = voice or EDGE_VOICES[0]['id']
        if voice not in {v['id'] for v in EDGE_VOICES}:
            raise ValueError('请选择列表中的 Edge 音色。')
    elif backend == 'volc':
        import volc_speech
        row, _ = volc_speech.configured()
        voice = voice or row['voice']
    else:
        import providers
        row, _ = providers.configured('tts')
        voice = voice or row.get('voice') or 'alloy'
    return voice


def duration(path):
    with wave.open(str(path), 'rb') as audio:
        seconds = audio.getnframes()/audio.getframerate()
    if seconds <= 0:
        raise ValueError('语音服务返回了空音频。')
    return seconds


def map_boundaries(text, events, seconds):
    """Preserve original punctuation; never guess times for missing words."""
    events = [event for event in events if norm(event['text'])]
    if not events or norm(''.join(e['text'] for e in events)) != norm(text):
        raise ValueError('语音时间戳与原文不一致，已保留音频供检查。可换用 Windows 离线音色；不能把估计时间当作对齐结果。')
    indices = [i for i, char in enumerate(text) if char.isalnum()]
    result, position, previous = [], 0, -1.0
    for index, event in enumerate(events):
        start = float(event['start'])
        end = float(event.get('end', events[index+1]['start'] if index+1 < len(events) else seconds))
        if not all(math.isfinite(t) for t in (start, end)) or start < 0 or start < previous or end <= start or end > seconds + .25:
            raise ValueError('语音服务返回无效时间戳，未生成字幕。')
        count = len(norm(event['text']))
        left = 0 if position == 0 else indices[position]
        position += count
        right = indices[position] if position < len(indices) else len(text)
        result.append({'text': text[left:right], 'start': start, 'end': min(end, seconds)})
        previous = start
    return result


def cues(words, limit=18):
    """Break captions only at actual synthesis word boundaries."""
    result, pending = [], None
    for word in words:
        if pending and len(norm(pending['text'] + word['text'])) > limit:
            result.append(pending)
            pending = None
        if pending is None:
            pending = dict(word)
        else:
            pending['text'] += word['text']
            pending['end'] = word['end']
        if pending['text'].rstrip().endswith(('。', '！', '？', '；', '.', '!', '?', ';', '\n')):
            result.append(pending)
            pending = None
    if pending:
        result.append(pending)
    return result


def write_srt(path, rows):
    from providers import stamp
    Path(path).write_text('\n'.join(f'{i}\n{stamp(r["start"])} --> {stamp(r["end"])}\n{r["text"].strip()}\n'
                                   for i, r in enumerate(rows, 1)), encoding='utf-8')


async def _edge(text, voice, speed, path):
    import edge_tts
    events = []
    client = edge_tts.Communicate(text, voice, rate=f'{round((speed-1)*100):+d}%', boundary='WordBoundary',
                                  connect_timeout=15, receive_timeout=45)
    with path.open('wb') as output:
        async for chunk in client.stream():
            if chunk['type'] == 'audio':
                output.write(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                events.append({'text': html.unescape(chunk['text']), 'start': chunk['offset']/1e7,
                               'end': (chunk['offset']+chunk['duration'])/1e7})
    return events


def synthesize(text, output, backend='windows', voice='', speed=1.0, subtitles=True):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000 or not norm(text):
        raise ValueError('请输入 1–4000 字的配音文本。')
    voice = validate(backend, voice, speed)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Existing projects are never silently overwritten by an API request.
    for suffix in ('.alignment.json', '.srt', '.speech.json'):
        output.with_suffix(suffix).unlink(missing_ok=True)
    if backend == 'windows':
        with tempfile.TemporaryDirectory(prefix='speech-', dir=output.parent) as tmp:
            request = Path(tmp)/'request.json'
            write_json(request, {'text': text, 'voice': voice, 'rate': max(-10, min(10, round(10*math.log2(speed))))})
            events = powershell('-Action', 'speak', '-RequestPath', request, '-OutputPath', output)
        timing = 'synthesis-word-starts; ends use next word start or audio end'
    elif backend in ('edge', 'volc'):
        import imageio_ffmpeg
        mp3 = output.with_suffix('.source.mp3')
        if backend == 'edge':
            try:
                events = asyncio.run(asyncio.wait_for(_edge(text, voice, speed, mp3), timeout=180))
            except Exception:
                raise RuntimeError('Edge 在线配音连接失败或没有返回音频。请检查网络后重试，或切换 Windows 离线语音；不会自动上传到其他服务。') from None
        else:
            import volc_speech
            events = volc_speech.synthesize(text, mp3, voice, speed)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', str(mp3), '-ar', '24000', '-ac', '1',
                        '-c:a', 'pcm_s16le', str(output)], capture_output=True, check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        timing = 'synthesis-word-boundaries'
    else:
        import providers
        if subtitles:
            providers.configured('asr')
        providers.tts(text, output, voice, speed)
        events = providers.asr(output, output.with_suffix('.transcription.json'), words=True) if subtitles else []
        timing = 'asr-word-timestamps-checked-against-script' if subtitles else 'none'
    seconds = duration(output)
    metadata = {'backend': backend, 'voice': voice, 'speed': speed, 'duration': seconds, 'timing': timing,
                'gpu_required': False, 'subtitles': subtitles}
    if subtitles:
        aligned = map_boundaries(text, events, seconds)
        write_json(output.with_suffix('.alignment.json'), aligned)
        write_srt(output.with_suffix('.srt'), cues(aligned))
    write_json(output.with_suffix('.speech.json'), metadata)
    return metadata


def tts_project(project, spec):
    from creation_settings import voice_for
    for scene in spec['scenes']:
        voice = voice_for(spec, scene)
        synthesize(scene['narration'], project/'audio'/(scene['id']+'.wav'), spec['backends']['tts'],
                   voice.get('voice_id', ''), voice.get('speed', 1.0))


def align_project(project, spec):
    rows, timeline, offset = [], [], 0.0
    for scene in spec['scenes']:
        audio = project/'audio'/(scene['id']+'.wav')
        words = json.loads(audio.with_suffix('.alignment.json').read_text(encoding='utf-8'))
        seconds = duration(audio)
        # Recheck on resume: old or partial timestamps must not pass silently.
        words = map_boundaries(scene['narration'], words, seconds)
        rows.extend({**c, 'start': c['start']+offset, 'end': c['end']+offset} for c in cues(words))
        timeline.append({'id': scene['id'], 'start': offset, 'duration': seconds})
        offset += seconds
    write_srt(project/'subtitles.srt', rows)
    write_json(project/'timeline.json', timeline)

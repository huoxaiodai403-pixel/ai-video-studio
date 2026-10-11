"""Typed media operations used by the video Skills pipeline. No shell evaluation."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VIDEO = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}
IMAGE = {'.png', '.jpg', '.jpeg', '.webp'}
AUDIO = {'.wav', '.mp3', '.m4a', '.flac'}


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} 必须为 {low}–{high} 之间的数值')
    return value


def local_file(value, suffixes):
    from generation_plans import _plain
    if not isinstance(value, str) or value.startswith(('//', '\\\\')):
        raise ValueError('素材应为本机文件的绝对路径')
    path = Path(value)
    if not path.is_absolute() or path.suffix.lower() not in suffixes:
        raise ValueError('素材路径或文件类型不正确')
    path = _plain(path).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= 8 * 1024**3:
        raise ValueError('素材不存在、为空或超过 8 GB')
    return path


def ffmpeg():
    if (ROOT/'tools/ffmpeg.exe').is_file():
        return str(ROOT/'tools/ffmpeg.exe')
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def node():
    own = ROOT/'tools/node/node.exe'
    return str(own) if own.is_file() else shutil.which('node')

def ffprobe():
    for path in (ROOT/'tools/ffprobe.exe', ROOT/'tools/video-runtime/node_modules/ffprobe-static/bin/win32/x64/ffprobe.exe'):
        if path.is_file(): return str(path)
    return shutil.which('ffprobe')


def environment():
    env = os.environ.copy()
    probe = ROOT/'tools/video-runtime/node_modules/ffprobe-static/bin/win32/x64'
    env.update(PYTHONUTF8='1', FFMPEG_PATH=ffmpeg(), HF_HUB_DISABLE_TELEMETRY='1', HF_HOME=str(ROOT/'cache/huggingface'), DO_NOT_TRACK='1')
    browsers = list((ROOT/'tools/video-runtime/.remotion').glob('chrome-headless-shell/*/*/chrome-headless-shell.exe'))
    if browsers:
        env['HYPERFRAMES_BROWSER_PATH'] = str(browsers[0])
    env['PATH'] = os.pathsep.join([str(ROOT/'tools'), str(Path(ffmpeg()).parent), str(probe), str(Path(node()).parent) if node() else '', env.get('PATH', '')])
    return env


def run(command, dest, label='render', timeout=3600, *, provider_snapshot=None):
    dest = Path(dest)
    with (dest/(label+'.log')).open('w', encoding='utf-8') as log:
        import providers
        options = dict(cwd=dest, env=environment(), stdout=log, stderr=subprocess.STDOUT,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        process = (providers.start_worker(command, provider_snapshot, **options) if provider_snapshot is not None
                   else subprocess.Popen([str(x) for x in command], **options))
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)
            else:
                process.kill(); process.wait()
            raise RuntimeError(f'{label} 超时，已停止本次任务')
    if code:
        # Keep detailed command diagnostics in the local project, never expose credentials in an API error.
        raise RuntimeError(f'{label} 执行失败（退出码 {code}），请查看工程 {label}.log')


def probe(path):
    import av
    with av.open(str(path)) as media:
        video = next(iter(media.streams.video), None)
        seconds = float(media.duration / av.time_base) if media.duration is not None else 0
        if video and not seconds and video.duration is not None:
            seconds = float(video.duration * video.time_base)
        if seconds <= 0:
            raise ValueError('媒体没有可读取的实际时长')
        result = {'duration': seconds, 'audio': bool(media.streams.audio)}
        if video:
            result.update(width=video.width, height=video.height, fps=float(video.average_rate or 0))
        return result


def cues(value, duration=None):
    if not isinstance(value, list) or not 1 <= len(value) <= 1000:
        raise ValueError('字幕应包含 1–1000 个带实际时间的片段')
    result, end = [], 0
    for item in value:
        if not isinstance(item, dict) or set(item) - {'start', 'end', 'text'}:
            raise ValueError('字幕片段只接受 start、end、text')
        start = number(item.get('start'), '字幕起点', 0, 14400)
        stop = number(item.get('end'), '字幕终点', 0, 14400)
        text = item.get('text')
        if start < end - .001 or stop <= start or duration and stop > duration + .1:
            raise ValueError('字幕时间必须有序、无重叠且处于媒体实际时长内')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or '\x00' in text:
            raise ValueError('每段字幕需要 1–2000 字正文')
        result.append({'start': start, 'end': stop, 'text': text.strip()})
        end = stop
    return result


def read_srt(path, duration=None):
    text = Path(path).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    result = []
    pattern = r'(\d{2,}):(\d{2}):(\d{2})[,\.](\d{3})'
    def seconds(parts):
        h, m, s, ms = map(int, parts)
        if m > 59 or s > 59: raise ValueError('字幕时间格式错误')
        return h*3600+m*60+s+ms/1000
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit(): lines.pop(0)
        if not lines: continue
        match = re.fullmatch(pattern+r'\s+-->\s+'+pattern, lines.pop(0).strip())
        if not match: raise ValueError('请提供标准 UTF-8 SRT 字幕')
        result.append({'start': seconds(match.groups()[:4]), 'end': seconds(match.groups()[4:]), 'text': '\n'.join(lines)})
    return cues(result, duration)


def write_cues(dest, rows):
    from providers import stamp
    rows = cues(rows)
    dest = Path(dest)
    dest.with_suffix('.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    dest.with_suffix('.srt').write_text('\n\n'.join(f'{i}\n{stamp(r["start"])} --> {stamp(r["end"])}\n{r["text"]}' for i, r in enumerate(rows, 1))+'\n', encoding='utf-8')
    dest.with_suffix('.vtt').write_text('WEBVTT\n\n'+'\n\n'.join(f'{stamp(r["start"]).replace(",", ".")} --> {stamp(r["end"]).replace(",", ".")}\n{r["text"]}' for r in rows)+'\n', encoding='utf-8')


def encode_options(fps=24):
    return ['-r', str(fps), '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-threads', '4', '-c:a', 'aac', '-ar', '48000', '-movflags', '+faststart']


def burn(source, rows, dest):
    write_cues(dest/'subtitles', rows)
    run([ffmpeg(), '-y', '-i', source, '-vf', "subtitles=subtitles.srt:force_style='FontName=Microsoft YaHei,FontSize=22,Outline=2,MarginV=24'", *encode_options(probe(source).get('fps', 24)), dest/'video.mp4'], dest, 'subtitles')
    return dest/'video.mp4'


def cut_video(source, options, dest):
    meta = probe(source)
    ranges = options.get('cuts') or [{'start': 0, 'end': meta['duration']}]
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 100:
        raise ValueError('请提供 1–100 段剪辑范围')
    width, height = int(options.get('width', meta['width'])), int(options.get('height', meta['height']))
    number(width, '宽度', 64, 3840); number(height, '高度', 64, 3840)
    if width % 2 or height % 2: raise ValueError('视频宽高必须为偶数')
    fps = number(options.get('fps', meta['fps']), '帧率', 1, 60)
    speed = number(options.get('speed', 1), '播放速度', .5, 2)
    volume = number(options.get('volume', 1), '音量', 0, 3)
    fit = options.get('fit', 'pad')
    if fit not in {'pad', 'crop'}: raise ValueError('画幅模式应为 pad 或 crop')
    vf = f'scale={width}:{height}:force_original_aspect_ratio=' + ('decrease,pad='+f'{width}:{height}:(ow-iw)/2:(oh-ih)/2' if fit == 'pad' else 'increase,crop='+f'{width}:{height}')
    vf += ',setsar=1,setpts=PTS/'+str(speed)
    segments = []
    for index, row in enumerate(ranges):
        if not isinstance(row, dict) or set(row) != {'start', 'end'}: raise ValueError('剪辑范围只接受 start 与 end')
        start = number(row['start'], '剪辑起点', 0, meta['duration'])
        end = number(row['end'], '剪辑终点', 0, meta['duration']+.05)
        if end <= start: raise ValueError('剪辑终点必须晚于起点')
        output = dest/f'cut-{index:03d}.mp4'
        upstream = ROOT/'tools/video-skills/ffmpeg-skill/scripts/cut.py'
        raw = dest/f'raw-{index:03d}.mp4'
        if upstream.is_file():
            run([sys.executable, upstream, source, '--start', str(start), '--end', str(end), '--accurate', '-o', raw], dest, f'cut-{index:03d}')
            inputs = ['-i', raw]
        else:
            raise ValueError('FFmpeg Skill 未安装，请运行 Install-VideoTools.ps1')
        run([ffmpeg(), '-y', *inputs, '-vf', vf, '-af', f'atempo={speed},volume={volume}', *encode_options(fps), output], dest, f'fit-{index:03d}')
        segments.append(output)
    (dest/'segments.txt').write_text('\n'.join("file '"+p.name+"'" for p in segments), encoding='utf-8')
    run([ffmpeg(), '-y', '-f', 'concat', '-safe', '0', '-i', 'segments.txt', '-c', 'copy', '-movflags', '+faststart', 'video.mp4'], dest, 'join')
    return dest/'video.mp4'


def atempo(rate):
    filters = []
    while rate > 2: filters.append('atempo=2'); rate /= 2
    while rate < .5: filters.append('atempo=0.5'); rate /= .5
    return ','.join(filters+[f'atempo={rate:.8f}'])

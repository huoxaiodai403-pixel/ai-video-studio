"""CPU renderer for original, self-contained HTML animations authored by Codex.

The HTTP process only validates JSON and starts a separate Node/Chromium worker.
The document has no Node bindings, host file origin, network, or workbench APIs.
All visual state must be computed by window.renderFrame(timeSeconds).
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_HTML_BYTES = 2_000_000
MAX_SCRIPT_BYTES = 256_000
MAX_ELEMENTS = 5_000
MAX_FRAMES = 1_800
MAX_PIXEL_FRAMES = 1_500_000_000
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.aac', '.ogg', '.flac'}


class _DocumentCheck(HTMLParser):
    """Helpful preflight; browser isolation, not parsing, is the security boundary."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = 0
        self.scripts = 0
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise ValueError('HTML 元素过多，最多 5000 个')
        if tag in {'iframe', 'frame', 'frameset', 'object', 'embed', 'base', 'link',
                   'form', 'input', 'audio', 'video', 'animate', 'animatetransform',
                   'animatemotion', 'set', 'foreignobject'}:
            raise ValueError(f'不支持 <{tag}>；请使用自包含 Canvas、SVG 或 DOM')
        values = dict(attrs)
        if tag == 'meta' and values.get('http-equiv', '').lower() in {'refresh', 'content-security-policy'}:
            raise ValueError('HTML 不能设置跳转或覆盖安全策略')
        for name, value in attrs:
            value = (value or '').strip()
            if name.startswith('on'):
                raise ValueError('请在 script 中定义 renderFrame，不使用 HTML 事件处理属性')
            if name in {'src', 'href', 'xlink:href', 'srcset', 'action', 'poster'}:
                if name == 'srcset' or not (value.startswith('#') or value.startswith('data:image/')):
                    raise ValueError('HTML 素材必须内嵌为 data:image，不能读取网络或本机文件')
        if tag == 'script':
            if 'src' in values or values.get('type', '').lower() == 'module':
                raise ValueError('请使用内联普通 JavaScript，不支持外部脚本或模块')
            self.in_script = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts += len(data.encode('utf-8'))
            if self.scripts > MAX_SCRIPT_BYTES:
                raise ValueError('内联脚本过大，最多 256 KB')


def _number(payload, key, default, minimum, maximum, integer=False):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{key} 必须是有限数值')
    if value < minimum or value > maximum or (integer and int(value) != value):
        raise ValueError(f'{key} 必须在 {minimum}–{maximum} 之间' + ('且为整数' if integer else ''))
    return int(value) if integer else float(value)


def normalize(payload: dict) -> dict:
    """Validate without starting a browser or reading audio content."""
    if not isinstance(payload, dict):
        raise ValueError('代码动画请求必须是对象')
    html = payload.get('html')
    if not isinstance(html, str) or not html.strip():
        raise ValueError('需要原创 HTML，并定义 window.renderFrame(timeSeconds)')
    if len(html.encode('utf-8')) > MAX_HTML_BYTES or '\x00' in html:
        raise ValueError('HTML 最多 2 MB，且不能包含空字符')
    if not re.search(r'\brenderFrame\b', html):
        raise ValueError('HTML 必须定义 window.renderFrame(timeSeconds)')
    # Deterministic frames cannot rely on elapsed real time or browser animation.
    if re.search(r'@(?:-webkit-)?keyframes\b|\b(?:animation|transition)(?:-[\w-]+)?\s*:', html, re.I):
        raise ValueError('禁止 CSS 动画/过渡；请在 renderFrame(timeSeconds) 中计算每帧状态')
    _DocumentCheck().feed(html)
    width = _number(payload, 'width', 1280, 256, 1920, True)
    height = _number(payload, 'height', 720, 256, 1920, True)
    fps = _number(payload, 'fps', 25, 1, 30, True)
    duration = _number(payload, 'duration', 6, 0.1, 60)
    if width % 2 or height % 2 or width * height > 1920 * 1080:
        raise ValueError('宽高必须是偶数，总像素不能超过 1920×1080')
    frames = math.ceil(duration * fps - 1e-9)
    if frames > MAX_FRAMES or frames * width * height > MAX_PIXEL_FRAMES:
        raise ValueError('渲染复杂度超限，请缩短镜头、降低分辨率或帧率')
    result = {'html': html, 'width': width, 'height': height, 'fps': fps,
              'duration': duration, 'frames': frames}
    if payload.get('audio_path') is not None:
        audio = payload['audio_path']
        if not isinstance(audio, str) or not audio or '\x00' in audio:
            raise ValueError('audio_path 必须是本地音频绝对路径')
        path = Path(audio)
        if not path.is_absolute() or audio.startswith(('\\\\', '//')) or path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError('audio_path 必须是本机 WAV/MP3/M4A/AAC/OGG/FLAC 的绝对路径')
        if not path.is_file() or path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('音频文件不存在，或是符号链接')
        if not 0 < path.stat().st_size <= 256_000_000:
            raise ValueError('音频文件必须非空且不超过 256 MB')
        resolved = path.resolve()
        if str(resolved).startswith(('\\\\', '//')):
            raise ValueError('不能通过目录链接读取网络共享音频')
        result['audio_path'] = str(resolved)
    return result


def _dependency(local: Path, command: str) -> Path:
    found = local if local.is_file() else shutil.which(command)
    if not found:
        raise RuntimeError(f'缺少 {command}，请运行 scripts/Install-Renderers.ps1')
    return Path(found).resolve()


def _worker_environment() -> dict:
    # Do not give browser workers the workbench's API credentials or proxy settings.
    allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA',
               'APPDATA', 'HOME', 'LANG', 'LC_ALL', 'FONTCONFIG_PATH'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'cache/ms-playwright')
    env['PYTHONUTF8'] = '1'
    return env


def _run_worker(command: list[str], cwd: Path, timeout: float):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen(command, cwd=str(cwd), env=_worker_environment(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace', creationflags=flags,
                               start_new_session=os.name != 'nt')
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if os.name == 'nt':
            subprocess.run([str(Path(os.environ.get('SYSTEMROOT', r'C:\Windows')) / 'System32/taskkill.exe'),
                            '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=flags, timeout=15)
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=15)
        raise RuntimeError('代码动画渲染超时；请简化 renderFrame 或缩短镜头') from error
    if process.returncode:
        raise RuntimeError('代码动画渲染失败: ' + (stderr.strip() or stdout.strip())[-2400:])
    return stdout


def render(payload: dict, dest: Path, preview: bool = False) -> dict:
    """Create a new isolated output set; never overwrite existing project products.

    Audio is muxed at time zero, trimmed/padded to the frame duration. No alignment
    or speech synthesis is inferred. Inspect qa.json for objective verification;
    editorial and listening acceptance always remain pending.
    """
    data = normalize(payload)
    if not isinstance(preview, bool):
        raise ValueError('preview 必须是布尔值')
    dest = Path(dest)
    if dest.is_symlink() or getattr(dest, 'is_junction', lambda: False)():
        raise ValueError('输出目录不能是链接')
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    names = ['sample.mp4' if preview else 'video.mp4', 'cover.png', 'scene.html', 'qa.json']
    if any((dest / name).exists() for name in names):
        raise ValueError('目标目录已有生成作品，请使用新目录保留旧版本')
    node = _dependency(ROOT / 'tools/node/node.exe', 'node')
    ffmpeg = _dependency(ROOT / 'tools/ffmpeg.exe', 'ffmpeg')
    frames = math.ceil(min(data['duration'], 3 if preview else 60) * data['fps'] - 1e-9)
    seconds = frames / data['fps']
    created = []
    stage = Path(tempfile.mkdtemp(prefix='.code-animation-', dir=dest)).resolve()
    try:
        (stage / 'scene.html').write_text(data['html'], encoding='utf-8')
        request = {key: data[key] for key in ('width', 'height', 'fps')}
        request.update(frames=frames, duration=seconds, video=names[0], ffmpeg=str(ffmpeg))
        if data.get('audio_path'):
            source = Path(data['audio_path'])
            # The document never receives the path or bytes of the user's audio.
            audio = stage / ('audio-input' + source.suffix.lower())
            shutil.copyfile(source, audio)
            request['audio_path'] = str(audio)
        (stage / 'request.json').write_text(json.dumps(request), encoding='utf-8')
        _run_worker([str(node), str(ROOT / 'scripts/render_code_animation.cjs'),
                     str(stage / 'request.json')], stage, timeout=min(900, 90 + frames * 2))
        worker = json.loads((stage / 'worker-result.json').read_text(encoding='utf-8'))
        if worker.get('frames') != frames or not worker.get('decoded'):
            raise RuntimeError('渲染帧数或解码验证未通过')
        for name in names[:3]:
            if not (stage / name).is_file() or (stage / name).stat().st_size == 0:
                raise RuntimeError(f'渲染缺少有效输出: {name}')
        metadata = {'engine': 'code-animation', 'renderer': 'playwright-ffmpeg-cpu',
                    'status': 'done', 'preview': preview, 'video': names[0], 'image': 'cover.png', 'cover': 'cover.png',
                    'source': 'scene.html', 'qa': 'qa.json', 'width': data['width'],
                    'height': data['height'], 'fps': data['fps'], 'frames': frames,
                    'duration': seconds, 'requested_duration': data['duration'],
                    'html_sha256': hashlib.sha256(data['html'].encode('utf-8')).hexdigest(),
                    'video_sha256': hashlib.sha256((stage / names[0]).read_bytes()).hexdigest(),
                    'quality_review': 'pending', 'visual_review': 'pending',
                    'audio': {'present': bool(data.get('audio_path')), 'alignment': 'not_performed',
                              'policy': 'start_at_zero_trim_or_silence_pad_to_video',
                              'listening_review': 'pending' if data.get('audio_path') else 'not_applicable'},
                    'checks': worker}
        (stage / 'qa.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        for name in names:
            # The API gives each render a fresh job directory. Exclusive creation
            # also protects against two callers accidentally using the same path.
            with (dest / name).open('xb') as output, (stage / name).open('rb') as source:
                created.append(dest / name)
                shutil.copyfileobj(source, output)
        return metadata
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        if stage.parent != dest or not stage.name.startswith('.code-animation-') or stage.is_symlink():
            raise RuntimeError('拒绝清理越界的渲染临时目录')
        shutil.rmtree(stage)

"""Local-only Jianying handoff. HTTP callers supply IDs, never file paths.

The HTTP process imports only standard-library modules. Draft writing runs in a
separate pinned environment. Existing Jianying drafts are never modified.
"""
import argparse
import configparser
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
from urllib.parse import quote
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}\Z')
SCENE_ID = re.compile(r'[A-Za-z0-9_-]{1,40}\Z')
MODES = ('auto', 'scenes', 'flattened')
BRIDGE_VERSION = '1'


def read(path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def _not_linked(path):
    """Reject symlink/junction ancestors, including links staying inside root."""
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('不允许符号链接或目录联接：' + str(path))


def project_path(project_id):
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise ValueError('工程 ID 无效')
    base = ROOT / 'projects/studio'
    path = base / project_id
    _not_linked(path)
    if not path.is_dir() or path.resolve().parent != base.resolve():
        raise ValueError('工程不存在')
    return path.resolve()


def contained(project, relative, *, required=True):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ':' in relative:
        raise ValueError('素材必须使用工程内的相对路径')
    path = project / relative
    _not_linked(path)
    if not path.resolve().is_relative_to(project.resolve()):
        raise ValueError('素材路径超出工程目录')
    if not path.is_file():
        if required:
            raise ValueError('工程素材缺失：' + relative)
        return None
    return path.resolve()


def _config():
    value = read(ROOT / 'config/jianying.json', {})
    if not isinstance(value, dict):
        raise ValueError('config/jianying.json 应为对象')
    return value


def discover():
    config = _config()
    local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    candidates = []
    if config.get('executable'):
        candidates.append(Path(config['executable']))
    for directory in (ROOT.parent / 'JianyingPro', local / 'JianyingPro/Apps', local / 'JianyingPro',
                      Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'JianyingPro',
                      Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'JianyingPro'):
        candidates.append(directory / 'JianyingPro.exe')
        if directory.is_dir():
            candidates.extend(sorted(directory.glob('*/JianyingPro.exe'), reverse=True))
    executable = next((p.resolve() for p in candidates if p.name.lower() == 'jianyingpro.exe' and p.is_file()), None)
    # Recent Jianying versions keep their index under AppData while the actual
    # draft directory can be elsewhere. Respect the app's own selected folder.
    app_settings = local / 'JianyingPro/User Data/Config/globalSetting'
    custom_root = None
    if app_settings.is_file():
        settings = configparser.ConfigParser(interpolation=None, strict=False)
        settings.read(app_settings, encoding='utf-8-sig')
        configured = settings.get('General', 'currentCustomDraftPath', fallback='').strip().strip('"')
        if configured:
            custom_root = Path(configured.replace('\\\\', '\\'))
    roots = ([Path(config['draft_root'])] if config.get('draft_root') else [custom_root] if custom_root else
             [local / 'JianyingPro/User Data/Projects/com.lveditor.draft'])
    draft_root = None
    for candidate in roots:
        if candidate.is_dir():
            _not_linked(candidate)
            if candidate.resolve() == Path(candidate.anchor):
                raise ValueError('剪映草稿位置不能是磁盘根目录')
            draft_root = candidate.resolve()
            break
    python = ROOT / 'apps/jianying-bridge/.venv/Scripts/python.exe'
    metadata = ROOT / 'apps/jianying-bridge/.venv/Lib/site-packages/pyjianyingdraft-0.3.0.dist-info/METADATA'
    return {'installed': executable is not None, 'executable': str(executable) if executable else None,
            'draft_root': str(draft_root) if draft_root else None,
            'bridge_ready': python.is_file() and metadata.is_file(),
            'bridge_version': 'pyJianYingDraft 0.3.0',
            'draft_root_source': 'studio-config' if config.get('draft_root') else 'jianying-settings' if custom_root else 'default',
            'desktop_export_available': False}


def _number(value, name, *, positive=False):
    if isinstance(value, bool):
        raise ValueError(name + ' 不是有效时间')
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(name + ' 不是有效时间') from None
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        raise ValueError(name + ' 必须是有效的正数/零')
    return result


def _wav_duration(path):
    with wave.open(str(path), 'rb') as audio:
        return audio.getnframes() / audio.getframerate()


def _probe(path):
    """Use bundled FFprobe, or the isolated writer's MediaInfo when absent."""
    probe = ROOT / 'tools/ffprobe.exe'
    if probe.is_file():
        result = subprocess.run([str(probe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                                capture_output=True, encoding='utf-8', check=True, timeout=30)
        value = json.loads(result.stdout)
        video = next((s for s in value['streams'] if s['codec_type'] == 'video'), {})
        if not video:
            raise ValueError('媒体没有可读取的视频轨道')
        numerator, _, denominator = str(video.get('r_frame_rate', '30/1')).partition('/')
        return {'duration': float(value['format']['duration']), 'width': int(video.get('width', 1920)),
                'height': int(video.get('height', 1080)), 'fps': round(float(numerator) / float(denominator or 1)) or 30}
    python = ROOT / 'apps/jianying-bridge/.venv/Scripts/python.exe'
    result = subprocess.run([str(python), '-X', 'utf8', str(Path(__file__)), '_probe', str(path)],
                            capture_output=True, encoding='utf-8', check=True, timeout=30)
    return json.loads(result.stdout)


@contextmanager
def _read_export_without_writer(path):
    """A read-sharing Windows handle rejects any active or new writing handle."""
    handle = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING. Keep this handle open
        # throughout probing so exporting cannot resume midway through inspection.
        handle = create(str(path), 0x80000000, 1, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError('文件仍在写入或被占用，请导出完成后刷新')
        close = kernel32.CloseHandle
        close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    try:
        yield
    finally:
        if handle is not None:
            close(handle)


def _inspect_export(path):
    """Container completion only; never implies visual or listening acceptance."""
    with _read_export_without_writer(path):
        before = path.stat()
        if time.time() - before.st_mtime < 3:
            raise ValueError('文件刚刚更新，请稍后刷新以确认写入结束')
        position, found = 0, set()
        with path.open('rb') as stream:
            while position < before.st_size:
                stream.seek(position)
                header = stream.read(8)
                if len(header) < 8:
                    raise ValueError('MP4 容器尚不完整')
                length, kind = int.from_bytes(header[:4], 'big'), header[4:]
                header_size = 8
                if length == 1:
                    extended = stream.read(8)
                    if len(extended) != 8:
                        raise ValueError('MP4 容器尚不完整')
                    length, header_size = int.from_bytes(extended, 'big'), 16
                # Unknown-length boxes are valid for streaming, but do not prove
                # that a desktop export is finalized. Do not surface them yet.
                if length < header_size or position + length > before.st_size:
                    raise ValueError('MP4 容器仍未封装完成')
                found.add(kind)
                position += length
        if not {b'ftyp', b'moov', b'mdat'}.issubset(found):
            raise ValueError('MP4 缺少完整的媒体索引或数据')
        media = _probe(path)
        if not math.isfinite(media['duration']) or media['duration'] <= 0 or media['width'] <= 0 or media['height'] <= 0:
            raise ValueError('MP4 媒体信息尚不可读')
        after = path.stat()
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError('MP4 检查过程中仍在变化')
        return media, after.st_size


def _subtitle_rows(path, duration):
    if path is None:
        return []
    rows = []
    stamp = re.compile(r'^(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})$')
    def seconds(value):
        match = stamp.fullmatch(value.strip())
        if not match:
            raise ValueError('SRT 时间格式无效')
        h, m, s, ms = map(int, match.groups())
        if m > 59 or s > 59:
            raise ValueError('SRT 时间范围无效')
        return h * 3600 + m * 60 + s + ms / 1000
    for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8-sig').strip()):
        lines = block.strip().splitlines()
        if not lines:
            continue
        if len(lines) < 3 or '-->' not in lines[1]:
            raise ValueError('SRT 字幕条目无效')
        left, right = lines[1].split('-->')
        start, end = seconds(left), min(seconds(right), duration)
        if end <= start or start >= duration:
            raise ValueError('SRT 字幕超出视频时长')
        if rows and start < rows[-1]['end'] - 0.001:
            raise ValueError('SRT 字幕时间重叠，请先修正')
        rows.append({'start': start, 'end': end, 'text': '\n'.join(lines[2:])})
    return rows


def _scene_plan(project, spec):
    scenes, timeline = spec.get('scenes'), read(project / 'timeline.json')
    if not isinstance(scenes, list) or not scenes or not isinstance(timeline, list):
        raise ValueError('缺少分镜与实测 timeline.json，只有整片交接可用')
    if len(scenes) > 500 or len(scenes) != len(timeline):
        raise ValueError('分镜数量与实测时间线不一致')
    result, ids, last_end = [], set(), 0.0
    media = {row.get('id'): row for row in spec.get('media', []) if isinstance(row, dict)}
    for scene, timing in zip(scenes, timeline):
        sid = scene.get('id')
        if not isinstance(sid, str) or not SCENE_ID.fullmatch(sid) or sid in ids or timing.get('id') != sid:
            raise ValueError('分镜 ID 或时间线顺序无效')
        ids.add(sid)
        start = _number(timing.get('start'), sid)
        duration = _number(timing.get('duration'), sid, positive=True)
        if abs(start - last_end) > 0.05:
            raise ValueError('分镜时间线必须连续，不能重叠或留出未知空隙')
        end = start + duration
        audio = contained(project, 'audio/' + sid + '.wav')
        audio_start = _number(timing.get('audio_start', start), sid)
        audio_duration = _wav_duration(audio)
        if audio_start < start or audio_start + audio_duration > end + 0.05:
            raise ValueError('旁白实长超出该分镜时间范围：' + sid)
        row = {'id': sid, 'start': start, 'duration': duration, 'audio': audio.relative_to(project).as_posix(),
               'audio_start': audio_start, 'audio_duration': min(audio_duration, end - audio_start),
               'speaker': str(scene.get('speaker') or '旁白')[:50], 'kind': 'card',
               'heading': str(scene.get('heading') or scene.get('board_title') or '')[:200],
               'text': str(scene.get('text') or '')[:4000],
               'points': [str(p)[:1000] for p in scene.get('points', scene.get('board_cards', []))][:8]}
        selected = media.get(scene.get('media_id'))
        if selected and scene.get('kind') in ('image', 'video'):
            source = contained(project, selected.get('path'))
            if selected.get('sha256') and file_sha(source) != selected['sha256']:
                raise ValueError('登记素材已经改变，请重新确认来源：' + sid)
            row.update(kind=scene['kind'], path=source.relative_to(project).as_posix(),
                       source_start=_number(scene.get('media_start', 0), sid))
        elif scene.get('kind') in ('image', 'video'):
            raise ValueError('分镜没有绑定有效的本地媒体：' + sid)
        else:
            # Rendered scene movies can include burnt-in subtitles; prefer original
            # visual assets or native editable cards rather than duplicate captions.
            motion = contained(project, 'motion/' + sid + '.mp4', required=False)
            image = contained(project, 'images/' + sid + '.png', required=False)
            if motion and spec.get('motion_enabled'):
                row.update(kind='video', path=motion.relative_to(project).as_posix(), source_start=0, fit_speed=True)
            elif image:
                row.update(kind='image', path=image.relative_to(project).as_posix(), source_start=0)
            elif not row['heading'] and not row['text'] and not row['points']:
                raise ValueError('分镜缺少可交接的画面素材或文字卡片：' + sid)
        result.append(row)
        last_end = end
    return result, last_end


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build_plan(project_id, mode='auto'):
    if mode not in MODES:
        raise ValueError('交接模式应为 auto、scenes 或 flattened')
    project = project_path(project_id)
    state = read(project / 'status.json', {})
    if not isinstance(state, dict) or state.get('status') != 'done':
        raise ValueError('请等待工程生成完成后再交接剪映')
    video = contained(project, 'video.mp4')
    geometry = _probe(video)
    spec = read(project / 'storyboard.json', {})
    if not isinstance(spec, dict):
        raise ValueError('storyboard.json 格式无效')
    rows, warnings, reason = [], [], None
    if mode != 'flattened':
        try:
            rows, duration = _scene_plan(project, spec)
        except ValueError as error:
            if mode == 'scenes':
                raise
            reason = str(error)
    actual_mode = 'scenes' if rows else 'flattened'
    plan = {'project_id': project_id, 'mode': actual_mode,
            'title': str(spec.get('title') or state.get('title') or project_id)[:120],
            'width': geometry['width'], 'height': geometry['height'], 'fps': geometry['fps'],
            'duration': duration if rows else geometry['duration'], 'scenes': rows, 'warnings': warnings,
            'source_video': 'video.mp4', 'bgm': None, 'subtitles': []}
    srt = contained(project, 'subtitles.srt', required=False)
    if rows:
        plan['subtitles'] = _subtitle_rows(srt, plan['duration'])
        warnings.append('独立镜头、角色旁白与字幕可编辑；原视频的转场、动效、自动音量避让不自动迁移。')
        if any(row['kind'] == 'card' for row in rows):
            warnings.append('讲解/白板画面重建为剪映原生文字卡片，手绘描边与原排版动画未迁移；整片模式可保留原成片外观。')
        bgm = spec.get('bgm', {'mode': 'none'})
        if isinstance(bgm, dict) and bgm.get('mode') != 'none':
            if bgm.get('mode') == 'media':
                item = next((m for m in spec.get('media', []) if m.get('id') == bgm.get('media_id') and m.get('kind') == 'audio'), None)
                if item:
                    source = contained(project, item.get('path'))
                    if item.get('sha256') and file_sha(source) != item['sha256']:
                        raise ValueError('配乐素材已改变，请重新确认')
                    plan['bgm'] = source.relative_to(project).as_posix()
            else:
                source = contained(project, 'ambient-original.wav', required=False)
                if source:
                    plan['bgm'] = source.relative_to(project).as_posix()
        if plan['bgm']:
            warnings.append('背景音乐以独立40%音量轨道交接；角色旁白保留原录音，可在剪映进一步调整响度。')
    else:
        warnings.append('整片模式：只有一个已混音/可能已烧字幕的视频片段，不能恢复分镜、角色音轨和画内文字。')
        if reason:
            warnings.append('自动回退原因：' + reason)
        if srt:
            warnings.append('SRT 作为附带文件保留，未重复叠加到已烧字幕的视频上。')
    files = {row[key] for row in rows for key in ('audio', 'path') if row.get(key)}
    if not rows:
        files.add('video.mp4')
    if plan['bgm']:
        files.add(plan['bgm'])
    if srt:
        files.add('subtitles.srt')
    plan['sources'] = {name: file_sha(contained(project, name)) for name in sorted(files)}
    return plan


def status(project_id=None):
    info = discover()
    info.update(editable_available=bool(info['installed'] and info['bridge_ready'] and info['draft_root']), project=None, last_export=None)
    action = ('ask_install' if not info['installed'] else 'install_bridge' if not info['bridge_ready']
              else 'first_launch' if not info['draft_root'] else 'ready')
    info['setup'] = {'action': action, 'requires_install_consent': not info['installed'],
                     'installer': 'scripts/Install-JianyingBridge.ps1',
                     'install_argument': '-InstallJianying' if not info['installed'] else None,
                     'download_url': 'https://www.capcut.cn/'}
    if project_id is not None:
        project = project_path(project_id)
        modes, reasons = [], {}
        for mode in ('scenes', 'flattened'):
            try:
                plan = build_plan(project_id, mode)
                modes.append(mode)
                reasons[mode] = plan['warnings']
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                reasons[mode] = [str(error)]
        latest = read(project / 'jianying/latest.json')
        if isinstance(latest, dict):
            latest = dict(latest)
            # Video deliverables are rechecked every read, including any future
            # persisted entries, so replacing a file with an active export hides it.
            latest['files'] = [item for item in latest.get('files', []) if isinstance(item, dict)
                               and item.get('kind') != 'video' and not str(item.get('url', '')).lower().endswith('.mp4')]
            latest['pending_files'] = []
            exports = project / 'jianying/exports'
            _not_linked(exports)
            if exports.is_dir():
                known = {item.get('url') for item in latest['files'] if isinstance(item, dict)}
                for candidate in sorted(exports.glob('*.mp4')):
                    _not_linked(candidate)
                    if candidate.is_file() and candidate.resolve().parent == exports.resolve():
                        url = _output_url(project_id, candidate.relative_to(project).as_posix())
                        if url not in known:
                            try:
                                media, size = _inspect_export(candidate)
                            except (ValueError, OSError, subprocess.SubprocessError) as error:
                                latest['pending_files'].append({'name': candidate.name, 'status': 'pending', 'reason': str(error)})
                                continue
                            latest['files'].append({'label': '剪映导出（待审） · ' + candidate.name, 'url': url,
                                                    'bytes': size, 'kind': 'video', 'duration': media['duration'],
                                                    'verification': {'container_readable': True, 'visual_review': 'pending',
                                                                     'audio_review': 'pending'}})
            info['last_export'] = latest
        info['project'] = {'project_id': project_id, 'can_export': bool(modes and info['editable_available']),
                           'available_modes': modes, 'mode_reasons': reasons}
    return info


@contextmanager
def _export_lock(project):
    path = project / 'jianying/export.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    _not_linked(path)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError('该工程正在交接剪映，请稍后查看交接状态') from None
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _output_url(project_id, relative):
    return '/outputs/' + quote(project_id, safe='') + '/' + quote(relative, safe='/')


def export_project(project_id, mode='auto'):
    project_path(project_id)
    if mode not in MODES:
        raise ValueError('交接模式无效')
    info = discover()
    if not info['bridge_ready']:
        raise ValueError('请先运行 scripts/Install-JianyingBridge.ps1 安装草稿桥接器')
    if not info['draft_root']:
        raise ValueError('尚未发现剪映草稿位置，请先启动剪映，或在本机 config/jianying.json 配置 draft_root')
    result = subprocess.run([str(ROOT / 'apps/jianying-bridge/.venv/Scripts/python.exe'), '-X', 'utf8',
                             str(Path(__file__)), '_export', project_id, '--mode', mode],
                            capture_output=True, encoding='utf-8', timeout=600)
    if result.returncode:
        # Worker errors are structured and omit tracebacks/private module internals.
        try:
            message = json.loads(result.stdout)['error']
        except (ValueError, KeyError):
            message = result.stderr[-1200:] or '剪映草稿生成失败'
        raise ValueError(message)
    return json.loads(result.stdout)


def _worker_export(project_id, mode):
    import pyJianYingDraft as draft
    from PIL import Image, ImageDraw

    project = project_path(project_id)
    info = discover()
    if not info['draft_root']:
        raise ValueError('未找到剪映草稿根目录')
    root = Path(info['draft_root'])
    with _export_lock(project):
        plan = build_plan(project_id, mode)
        fingerprint = hashlib.sha256(json.dumps({'version': BRIDGE_VERSION, 'root': str(root), 'plan': plan},
                                                ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        latest = read(project / 'jianying/latest.json', {})
        if latest.get('fingerprint') == fingerprint and Path(latest.get('draft_path', '')).parent == root:
            old = Path(latest['draft_path'])
            _not_linked(old)
            if (old / 'draft_content.json').is_file() and (old / 'studio-export.json').is_file():
                return dict(latest, reused=True)
        draft_id = uuid.uuid4().hex
        clean_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', plan['title']).strip(' .')[:42] or project_id
        name = 'Codex-' + clean_title + '-' + draft_id[:8]
        temporary_name = '.studio-' + draft_id
        staging, destination = root / temporary_name, root / name
        if staging.exists() or destination.exists():
            raise ValueError('新的草稿目录发生冲突，请重试')
        script = draft.DraftFolder(str(root)).create_draft(temporary_name, plan['width'], plan['height'],
                                                          fps=plan['fps'], allow_replace=False)
        assets = staging / 'assets'
        assets.mkdir()
        copied = {}
        for index, (relative, digest) in enumerate(plan['sources'].items()):
            source = contained(project, relative)
            target = assets / (f'{index:03d}-' + source.name)
            shutil.copy2(source, target)
            if file_sha(target) != digest:
                raise ValueError('复制期间原素材发生变化，请重新交接：' + relative)
            copied[relative] = target
        tracks = {}
        def track(kind, label):
            if label not in tracks:
                script.append_track(draft.TrackSpec(kind, label))
                tracks[label] = {'name': label, 'type': kind.name, 'segments': 0}
            return label
        def add(segment, kind, label):
            script.add_segment(segment, track(kind, label))
            tracks[label]['segments'] += 1
        def timerange(start, duration):
            return draft.trange(round(start * 1_000_000), round(duration * 1_000_000))
        if plan['mode'] == 'flattened':
            material = draft.VideoMaterial(str(copied['video.mp4']))
            add(draft.VideoSegment(material, draft.trange(0, material.duration)), draft.TrackType.video, '原成片（含混音）')
        else:
            background = assets / 'card-background.png'
            canvas = Image.new('RGB', (plan['width'], plan['height']), '#F3F2ED')
            painter = ImageDraw.Draw(canvas)
            painter.rectangle((0, 0, plan['width'], max(5, plan['height']//90)), fill='#24A88A')
            canvas.save(background)
            # Create visual tracks before text tracks for stable foreground ordering.
            track(draft.TrackType.video, '画面')
            for row in plan['scenes']:
                source = copied.get(row.get('path'), background)
                material = draft.VideoMaterial(str(source))
                clip_time = timerange(row['start'], row['duration'])
                options = {'volume': 0.0}
                if row['kind'] == 'video':
                    available = material.duration / 1_000_000
                    source_start = row.get('source_start', 0)
                    source_duration = available if row.get('fit_speed') else row['duration']
                    if source_start + source_duration > available + 0.001:
                        raise ValueError('分镜视频长度不够：' + row['id'])
                    options['source_timerange'] = timerange(source_start, min(source_duration, available - source_start))
                add(draft.VideoSegment(material, clip_time, **options), draft.TrackType.video, '画面')
            for row in plan['scenes']:
                clip_time = timerange(row['start'], row['duration'])
                if row['kind'] == 'card':
                    def text(value, label, y, size, bold=False):
                        if not value:
                            return
                        segment = draft.TextSegment(value, clip_time,
                            style=draft.TextStyle(size=size, bold=bold, color=(0.09, 0.15, 0.19), align=1,
                                                  auto_wrapping=True, max_line_width=0.82),
                            clip_settings=draft.ClipSettings(transform_y=y))
                        add(segment, draft.TrackType.text, label)
                    text(row['heading'], '标题', 0.65, 9.0, True)
                    if row['text']:
                        text(row['text'], '说明', 0.32, 5.0)
                    points = row['points']
                    for index, point in enumerate(points):
                        start_y = 0.30 if not row['text'] else 0.05
                        step = min(0.26, 0.85 / max(1, len(points)))
                        text(point.replace('｜', '  '), '要点' + str(index + 1), start_y - index * step, 5.0)
                audio = draft.AudioMaterial(str(copied[row['audio']]))
                duration = min(round(row['audio_duration'] * 1_000_000), audio.duration)
                add(draft.AudioSegment(audio, draft.trange(round(row['audio_start'] * 1_000_000), duration)),
                    draft.TrackType.audio, '配音 · ' + row['speaker'])
            if plan['bgm']:
                material = draft.AudioMaterial(str(copied[plan['bgm']]))
                offset, total = 0, round(plan['duration'] * 1_000_000)
                if material.duration <= 0:
                    raise ValueError('配乐长度无效')
                while offset < total:
                    duration = min(material.duration, total - offset)
                    add(draft.AudioSegment(material, draft.trange(offset, duration), volume=0.4), draft.TrackType.audio, '背景音乐')
                    offset += duration
            for subtitle in plan['subtitles']:
                segment = draft.TextSegment(subtitle['text'], timerange(subtitle['start'], subtitle['end'] - subtitle['start']),
                    style=draft.TextStyle(size=5.0, color=(1.0, 1.0, 1.0), align=1, auto_wrapping=True),
                    border=draft.TextBorder(color=(0.0, 0.0, 0.0), width=18),
                    clip_settings=draft.ClipSettings(transform_y=-0.82))
                add(segment, draft.TrackType.text, '字幕')
        script.save()
        # DraftFolder's bundled template has a shared ID/blank metadata: assign all
        # project identity fields before publishing this new directory.
        content = read(staging / 'draft_content.json')
        content['id'] = str(uuid.UUID(draft_id)).upper()
        content['name'] = name
        raw = json.dumps(content, ensure_ascii=False).replace(str(staging).replace('\\', '\\\\'), str(destination).replace('\\', '\\\\'))
        (staging / 'draft_content.json').write_text(raw, encoding='utf-8')
        meta = read(staging / 'draft_meta_info.json')
        meta.update(draft_id=content['id'], draft_name=name, draft_fold_path=str(destination), draft_root_path=str(root),
                    tm_duration=content['duration'], tm_draft_create=int(time.time()*1_000_000), tm_draft_modified=int(time.time()*1_000_000))
        write(staging / 'draft_meta_info.json', meta)
        relative = 'jianying/exports/' + draft_id + '.json'
        result = {'project_id': project_id, 'draft_id': draft_id, 'draft_name': name, 'draft_path': str(destination),
                  'mode': plan['mode'], 'duration': content['duration']/1_000_000, 'tracks': list(tracks.values()),
                  'warnings': plan['warnings'], 'created_at': time.time(), 'fingerprint': fingerprint, 'reused': False,
                  'manifest_url': _output_url(project_id, relative), 'delivery_dir': str(project / 'jianying/exports'),
                  'files': [{'label': '剪映交接清单', 'url': _output_url(project_id, relative)}],
                  'verification': {'draft_written': True, 'opened_in_jianying': False, 'exported_from_jianying': False}}
        write(staging / 'studio-export.json', result)
        (staging / 'README.txt').write_text('\n'.join([name, '本草稿由 AI Video Studio 创建，素材已复制到 assets。',
                                                     *plan['warnings'], '在剪映中打开与导出需单独验证。']), encoding='utf-8')
        staging.rename(destination)
        write(project / relative, result)
        write(project / 'jianying/latest.json', result)
        return result


def open_jianying(project_id=None):
    info = discover()
    if not info['executable']:
        raise ValueError('未发现已安装的剪映专业版')
    latest = None
    if project_id is not None:
        project = project_path(project_id)
        latest = read(project / 'jianying/latest.json')
    # Explicitly user-facing app launch, with a fixed discovered executable and no
    # shell, URI, command-line template, or untrusted draft path passed to it.
    process = subprocess.Popen([info['executable']], cwd=str(Path(info['executable']).parent))
    return {'opened': True, 'process_id': process.pid, 'last_export': latest,
            'message': '已启动剪映；请在首页打开 ' + latest['draft_name'] if latest else '已启动剪映',
            'draft_opened_automatically': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('status', 'open'):
        command = sub.add_parser(name)
        command.add_argument('--project')
    for name in ('export', '_export'):
        command = sub.add_parser(name)
        command.add_argument('project')
        command.add_argument('--mode', choices=MODES, default='auto')
    sub.add_parser('doctor')
    probe = sub.add_parser('_probe')
    probe.add_argument('path')
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            import importlib.metadata
            import pyJianYingDraft
            import pymediainfo
            if importlib.metadata.version('pyjianyingdraft') != '0.3.0' or not pymediainfo.MediaInfo.can_parse():
                raise ValueError('草稿库版本或 MediaInfo 不可用')
            result = {'ready': True, 'version': '0.3.0'}
        elif args.command == '_probe':
            import pymediainfo
            media = pymediainfo.MediaInfo.parse(args.path)
            video = media.video_tracks[0]
            result = {'duration': float(media.general_tracks[0].duration)/1000, 'width': video.width,
                      'height': video.height, 'fps': round(float(video.frame_rate or 30))}
        elif args.command == 'status':
            result = status(args.project)
        elif args.command == 'open':
            result = open_jianying(args.project)
        else:
            result = (_worker_export if args.command == '_export' else export_project)(args.project, args.mode)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

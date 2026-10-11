"""Human review of actual deliverables, versioned independently of render success."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs

from filelock import FileLock
import av
import generation_plans as plans
import library_api
from prompt_library import ROOT

LOCK = threading.RLock()
CHECKS = {'meaning': '内容与画面', 'type': '文字与字幕', 'motion': '动作与连续性',
          'sound': '声音与同步', 'ending': '片尾与交付'}
VALUES = {'pending', 'pass', 'issue', 'na'}


class ReviewConflict(ValueError):
    pass


def _item(identity, jobs=None):
    if not isinstance(identity, str) or not re.fullmatch(r'lib-[a-f0-9]{24}', identity):
        raise ValueError('请从作品库选择已有视频')
    item = next((row for row in library_api.catalog(status='all', jobs=jobs)['items'] if row['id'] == identity), None)
    if not item or item['media_type'] != 'video' or not item.get('absolute_path'):
        raise ValueError('该作品尚无可审看的视频，请先生成样片或成片')
    path = plans._plain(Path(item['absolute_path']))
    base = plans._plain(ROOT.resolve() / 'projects/studio')
    if not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('只能审看工作台工程中的实际视频')
    owner = plans._plain(base / path.relative_to(base).parts[0])
    stamp = path.stat()
    fingerprint = hashlib.sha256((path.relative_to(base).as_posix() + ':' +
                                  str(stamp.st_size) + ':' + str(stamp.st_mtime_ns)).encode()).hexdigest()
    # Container metadata is read from this file; planned lengths are never used.
    with av.open(str(path)) as media:
        stream = next(iter(media.streams.video), None)
        if stream is None:
            raise ValueError('文件没有可播放的视频轨道')
        duration = float(stream.duration * stream.time_base) if stream.duration is not None else (
            float(media.duration / av.time_base) if media.duration is not None else 0)
        fps = float(stream.average_rate) if stream.average_rate else None
        geometry = {'duration': duration, 'fps': fps, 'width': stream.width, 'height': stream.height,
                    'has_audio': bool(media.streams.audio)}
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('无法读取实际视频时长')
    return item, owner, fingerprint, geometry


def _path(owner, identity):
    return plans._plain(owner / 'reviews' / (identity + '.json'))


def _read(path):
    return plans._json(path) if path.is_file() else None


def load(identity, jobs=None):
    item, owner, fingerprint, media = _item(identity, jobs)
    stored = _read(_path(owner, identity))
    stale = bool(stored and stored['media_fingerprint'] != fingerprint)
    review = {'revision': stored['revision'] if stored else 0, 'media_fingerprint': fingerprint,
              'verdict': 'pending', 'checks': dict.fromkeys(CHECKS, 'pending'), 'notes': [], 'updated_at': None}
    if stored and not stale:
        review.update({key: stored[key] for key in review})
    return {'item': {key: item.get(key) for key in ('id', 'title', 'status', 'project_id', 'preview_url', 'edit_url', 'source_url')},
            'media': media, 'review': review, 'stale': stale,
            'previous_review': {key: stored[key] for key in review} if stale else None,
            'criteria': CHECKS}


def save(data, jobs=None):
    fields = {'id', 'revision', 'media_fingerprint', 'verdict', 'checks', 'notes'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('审片记录只接受作品 ID、版本、检查项、结论和时间标记')
    if type(data['revision']) is not int or data['revision'] < 0:
        raise ValueError('审片版本无效')
    if not isinstance(data['verdict'], str) or data['verdict'] not in {'pending', 'needs-fix', 'approved'}:
        raise ValueError('请选择待审看、需要返修或审看通过')
    checks = data['checks']
    if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(not isinstance(v, str) or v not in VALUES for v in checks.values()):
        raise ValueError('请填写五项审片检查')
    if not isinstance(data['notes'], list) or len(data['notes']) > 200:
        raise ValueError('每份审片记录最多 200 个时间标记')
    notes, identities = [], set()
    for raw in data['notes']:
        if not isinstance(raw, dict) or set(raw) != {'id', 'seconds', 'category', 'text', 'resolved'}:
            raise ValueError('时间标记字段无效')
        if not isinstance(raw['id'], str) or not re.fullmatch(r'[a-f0-9]{32}', raw['id']) or raw['id'] in identities:
            raise ValueError('时间标记 ID 无效或重复')
        identities.add(raw['id'])
        if not isinstance(raw['category'], str) or raw['category'] not in CHECKS or type(raw['resolved']) is not bool:
            raise ValueError('标记分类或处理状态无效')
        if type(raw['seconds']) not in (int, float) or not math.isfinite(raw['seconds']) or raw['seconds'] < 0:
            raise ValueError('标记时间应为有效秒数')
        notes.append({**raw, 'seconds': round(raw['seconds'], 3),
                      'text': plans._text(raw['text'], '返修说明', 2000, 1)})
    if data['verdict'] == 'approved' and (any(v not in {'pass', 'na'} for v in checks.values())
                                         or any(not note['resolved'] for note in notes)):
        raise ValueError('请完成五项检查并处理全部标记，再确认审看通过')
    with LOCK:
        item, owner, fingerprint, media = _item(data['id'], jobs)
        folder = plans._plain(owner / 'reviews')
        folder.mkdir(exist_ok=True)
        lock_path = plans._plain(folder / 'review.lock')
        with FileLock(str(lock_path), timeout=5):
            path = _path(owner, data['id'])
            stored = _read(path)
            revision = stored['revision'] if stored else 0
            if data['revision'] != revision:
                raise ReviewConflict('审片记录已在其他页面更新；请保留当前文字，重新读取后再保存')
            if data['media_fingerprint'] != fingerprint:
                raise ReviewConflict('视频文件已更新；旧版本检查不能应用到新文件，请重新审看')
            if any(note['seconds'] > media['duration'] + .05 for note in notes):
                raise ValueError('标记时间超出实际视频时长')
            history = copy.deepcopy(stored.get('history', [])) if stored else []
            if stored and stored['media_fingerprint'] != fingerprint:
                history.append({key: value for key, value in stored.items() if key != 'history'})
            result = {**data, 'notes': notes, 'revision': revision + 1, 'updated_at': time.time(),
                      'history': history[-20:]}
            plans._atomic(path, result)
    return load(data['id'], jobs)


def get(handler, route, jobs=None):
    if route.path != '/api/review':
        return False
    try:
        query = parse_qs(route.query, keep_blank_values=True)
        if set(query) != {'id'} or len(query['id']) != 1:
            raise ValueError('请提供单个作品 ID')
        handler.reply(load(query['id'][0], jobs))
    except (ValueError, OSError, av.FFmpegError) as exc:
        handler.reply({'error': str(exc)}, 400)
    return True


def post(handler, data, jobs=None):
    if handler.path != '/api/review':
        return False
    try:
        handler.reply(save(data, jobs))
    except ReviewConflict as exc:
        handler.reply({'error': str(exc)}, 409)
    except (ValueError, OSError, av.FFmpegError) as exc:
        handler.reply({'error': str(exc)}, 400)
    return True

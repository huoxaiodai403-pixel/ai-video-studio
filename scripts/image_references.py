"""Validated local reference images and immutable per-job copies."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid
from urllib.parse import parse_qs

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT/'assets/image-references'
LOCK = threading.RLock()
MAX_BYTES = 12*1024*1024
MAX_PIXELS = 16*1024*1024
FORMATS = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'img-[a-f0-9]{24}', value):
        raise ValueError('无效的参考图 ID')
    return value


def resolve(value, verify=True):
    value = identity(value)
    info = STORE/(value+'.json')
    if not info.is_file():
        raise ValueError('参考图不存在，请重新登记')
    row = json.loads(info.read_text(encoding='utf-8'))
    path = (STORE/row['file']).resolve()
    if not path.is_relative_to(STORE.resolve()) or not path.is_file() or path.suffix not in FORMATS.values():
        raise ValueError('参考图文件缺失或越界')
    if verify and digest(path) != row['sha256']:
        raise ValueError('参考图已被修改，请重新登记')
    return {**row, 'path': str(path), 'preview_url': '/api/image-references/preview?id='+value}


def catalog():
    with LOCK:
        rows = [resolve(path.stem, verify=False) for path in STORE.glob('img-*.json')]
    return sorted(rows, key=lambda row: row['created_at'], reverse=True)


def register(raw, name):
    if not isinstance(raw, bytes) or not 100 <= len(raw) <= MAX_BYTES:
        raise ValueError('参考图应为不超过 12 MB 的 PNG、JPEG 或 WebP')
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('参考图名称应为 1–200 字')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            kind = image.format
            if kind not in FORMATS or width < 64 or height < 64 or width*height > MAX_PIXELS:
                raise ValueError('参考图需为 PNG/JPEG/WebP，每边至少 64 像素，总像素不超过 1600 万')
            if getattr(image, 'is_animated', False):
                raise ValueError('请使用单帧参考图')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('参考图不能完整解码') from exc
    sha = hashlib.sha256(raw).hexdigest()
    ref_id = 'img-'+sha[:24]
    with LOCK:
        STORE.mkdir(parents=True, exist_ok=True)
        if (STORE/(ref_id+'.json')).is_file():
            return resolve(ref_id)
        target = STORE/(ref_id+FORMATS[kind])
        temporary = target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
        temporary.write_bytes(raw)
        os.replace(temporary, target)
        write(STORE/(ref_id+'.json'), {'id': ref_id, 'name': Path(name).name, 'file': target.name,
              'width': width, 'height': height, 'sha256': sha, 'bytes': len(raw), 'created_at': time.time()})
    return resolve(ref_id)


def validate_ids(values):
    if not isinstance(values, list) or len(values) > 4 or len(set(map(str, values))) != len(values):
        raise ValueError('参考图最多 4 张且不能重复')
    return [resolve(value) for value in values]


def freeze(values, project):
    rows = validate_ids(values)
    project = Path(project).resolve()
    if not project.is_relative_to((ROOT/'projects').resolve()):
        raise ValueError('参考图快照须保存到项目目录')
    frozen = []
    for row in rows:
        source = Path(row['path'])
        target = project/'references'/source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if digest(target) != row['sha256']:
            raise ValueError('项目参考图快照与已登记图像不一致')
        frozen.append({**row, 'path': str(target), 'project_path': target.relative_to(project).as_posix()})
    return frozen


def checked_paths(rows):
    if not isinstance(rows, list) or len(rows) > 4:
        raise ValueError('参考图快照最多 4 张')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('参考图快照格式错误')
        path = Path(row.get('path', '')).resolve()
        allowed = path.is_relative_to(STORE.resolve()) or path.is_relative_to((ROOT/'projects').resolve())
        if not allowed or not path.is_file() or path.suffix.lower() not in FORMATS.values():
            raise ValueError('参考图快照文件缺失或越界')
        if digest(path) != row.get('sha256'):
            raise ValueError('参考图快照已变更，请重新登记和提交')
        result.append(path)
    return result


def freeze_storyboard(spec, project):
    for scene in spec.get('scenes', []):
        scene.pop('image_references',None)
        values = scene.get('image_reference_ids', spec.get('image_reference_ids', []))
        if values:
            if spec.get('backends', {}).get('image', 'local') != 'local' or spec['settings']['image']['engine'] != 'flux2-klein-4b':
                raise ValueError('参考图编辑目前需要本地 FLUX.2 klein 4B')
            scene['image_references'] = freeze(values, project)
    return spec


def get(handler, route):
    if route.path == '/api/image-references':
        handler.reply({'references': catalog()})
        return True
    if route.path == '/api/image-references/preview':
        try:
            row = resolve(parse_qs(route.query).get('id', [''])[0])
            handler.send_file(Path(row['path']))
        except (ValueError, OSError) as exc:
            handler.reply({'error': str(exc)}, 400)
        return True
    return False


def post(handler, data):
    if handler.path != '/api/image-references':
        return False
    if set(data) == {'job_id'}:
        job = data['job_id']
        if not isinstance(job, str) or not re.fullmatch(r'[a-f0-9]{12}', job):
            raise ValueError('请选择一个已完成的插画任务')
        folder = ROOT/'projects/studio'/job
        if not (folder/'status.json').is_file() or json.loads((folder/'status.json').read_text(encoding='utf-8'))['status'] != 'done':
            raise ValueError('插画任务尚未完成')
        row = register((folder/'image.png').read_bytes(), '生成图-'+job+'.png')
    elif set(data) == {'name', 'base64'}:
        try:
            raw = base64.b64decode(data['base64'], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError('参考图编码无效') from exc
        row = register(raw, data['name'])
    else:
        raise ValueError('请上传参考图或选择已完成的插画任务')
    handler.reply({'reference': row, 'references': catalog()})
    return True

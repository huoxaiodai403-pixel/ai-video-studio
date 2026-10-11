"""CPU animation assembly and isolated Blender previs workers. No model imports."""
import argparse
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def number(value, name, low, high, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or not low <= value <= high or integer and int(value) != value):
        raise ValueError(f'{name} 应为 {low}–{high}' + (' 的整数' if integer else ''))
    return int(value) if integer else float(value)


def blender_path():
    candidates = [ROOT / 'apps/blender/blender.exe']
    candidates.extend(sorted((ROOT/'apps').glob('blender-*/blender.exe'), reverse=True))
    if value := os.environ.get('AI_VIDEO_BLENDER'):
        candidates.insert(0, Path(value))
    if value := shutil.which('blender'):
        candidates.append(Path(value))
    for prefix in (Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Blender Foundation',):
        if prefix.is_dir():
            candidates.extend(sorted(prefix.glob('Blender */blender.exe'), reverse=True))
    return next((p.resolve() for p in candidates if p.is_file()), None)


def normalize(kind, payload):
    if not isinstance(payload, dict):
        raise ValueError('生成参数应为对象')
    if kind == 'character-loop':
        frames = payload.get('frames')
        if not isinstance(frames, list) or not 4 <= len(frames) <= 120:
            raise ValueError('请提供 4–120 张真实动作姿势图片，按播放顺序排列')
        paths = []
        for value in frames:
            if not isinstance(value, str) or not value.strip():
                raise ValueError('姿势图片路径不能为空')
            path = Path(value)
            from generation_plans import _plain
            _plain(path)
            if value.startswith(('\\\\', '//')):
                raise ValueError('姿势图片必须来自本机，不能使用网络共享')
            if (not path.is_absolute() or not path.is_file() or path.suffix.lower() not in ('.png', '.webp', '.jpg', '.jpeg')
                    or path.stat().st_size > 30 * 1024 * 1024):
                raise ValueError('姿势图片必须是本机现有 PNG/WebP/JPG，每张不超过 30 MB')
            paths.append(str(path.resolve()))
        background = payload.get('background', 'transparent')
        if background not in ('transparent', 'green'):
            raise ValueError('背景应选择 transparent 或 green')
        return {'frames': paths, 'width': number(payload.get('width', 512), '宽度', 64, 1024, True),
                'height': number(payload.get('height', 512), '高度', 64, 1024, True),
                'fps': number(payload.get('fps', 8), '帧率', 2, 25, True), 'background': background}
    if kind == 'blender-previs':
        result = {'width': number(payload.get('width', 640), '宽度', 160, 1920, True),
                  'height': number(payload.get('height', 360), '高度', 120, 1080, True),
                  'fps': number(payload.get('fps', 24), '帧率', 6, 30, True),
                  'duration': number(payload.get('duration', 4), '时长', 1, 20),
                  'distance': number(payload.get('distance', 6), '机位距离', 3, 20),
                  'camera': payload.get('camera', 'orbit'), 'subject': payload.get('subject', 'sphere')}
        if result['camera'] not in ('orbit', 'push', 'static') or result['subject'] not in ('sphere', 'cube'):
            raise ValueError('预演支持 orbit/push/static 运镜及 sphere/cube 主体')
        if result['width'] % 2 or result['height'] % 2:
            raise ValueError('预演宽高应为偶数')
        objects = payload.get('objects', [])
        if not isinstance(objects, list) or len(objects) > 12:
            raise ValueError('预演最多 12 个几何对象')
        result['objects'] = []
        for index, item in enumerate(objects):
            if not isinstance(item, dict) or item.get('shape') not in ('sphere', 'cube', 'cylinder'):
                raise ValueError('对象形状应为 sphere/cube/cylinder')
            obj = {'shape': item['shape'], 'name': str(item.get('name', f'actor-{index+1}'))[:60]}
            for name, default in [('start', [0, 0, 1]), ('end', [0, 0, 1]), ('scale', [1, 1, 1])]:
                values = item.get(name, default)
                if not isinstance(values, list) or len(values) != 3:
                    raise ValueError(f'{name} 必须含三个坐标')
                obj[name] = [number(v, name, .05 if name == 'scale' else -20, 20) for v in values]
            result['objects'].append(obj)
        return result
    raise ValueError('未知生成类型')


def edge_green(image):
    """Only remove key-colour pixels connected to the outer edge, preserving enclosed green."""
    image = image.copy().convert('RGBA')
    w, h = image.size
    pixels = image.load()
    seen = bytearray(w * h)
    queue = deque()
    def visit(x, y):
        pos = y * w + x
        if seen[pos]:
            return
        seen[pos] = 1
        r, g, b, a = pixels[x, y]
        if a == 0 or g > 70 and g > r * 1.35 and g > b * 1.35:
            pixels[x, y] = (r, g, b, 0)
            queue.append((x, y))
    for x in range(w):
        visit(x, 0); visit(x, h - 1)
    for y in range(h):
        visit(0, y); visit(w - 1, y)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if 0 <= nx < w and 0 <= ny < h:
                visit(nx, ny)
    return image


def render_loop(payload, dest, preview=False):
    from PIL import Image, ImageChops, ImageStat
    spec = normalize('character-loop', payload)
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    source_dir = dest / 'poses'; source_dir.mkdir(exist_ok=True)
    images, hashes = [], []
    source_size = None
    for index, source in enumerate(spec['frames']):
        with Image.open(source) as opened:
            if opened.width * opened.height > 16_000_000:
                raise ValueError('姿势图像像素数不得超过 1600 万')
            image = opened.convert('RGBA')
        if source_size and image.size != source_size:
            raise ValueError('姿势图需要相同画布尺寸和角色锚点，请先由 Codex 整理')
        source_size = image.size
        hashes.append(hashlib.sha256(image.tobytes()).hexdigest())
        image.save(source_dir / f'{index:04d}.png')
        image.thumbnail((spec['width'], spec['height']), Image.Resampling.LANCZOS)
        if spec['background'] == 'green':
            image = edge_green(image)
        canvas = Image.new('RGBA', (spec['width'], spec['height']))
        canvas.alpha_composite(image, ((spec['width']-image.width)//2, (spec['height']-image.height)//2))
        images.append(canvas)
    if len(set(hashes)) < 4:
        raise ValueError('至少需要四张不同的真实姿势；重复静帧不能当作角色动作生成')
    images[0].save(dest / 'cover.png')
    indexed = []
    for rgba in images:
        palette = rgba.convert('RGB').quantize(colors=255, method=Image.Quantize.MEDIANCUT)
        # Reserve 255 exclusively for transparent pixels. GIF alpha is binary.
        alpha = rgba.getchannel('A').point(lambda a: 255 if a < 128 else 0)
        palette.paste(255, mask=alpha)
        palette.info['transparency'] = 255
        indexed.append(palette)
    frame_ms = max(10, round(100 / spec['fps']) * 10)
    indexed[0].save(dest / 'animation.gif', save_all=True, append_images=indexed[1:],
                    duration=frame_ms, loop=0, transparency=255, disposal=2, optimize=False)
    images[0].save(dest / 'animation.webp', save_all=True, append_images=images[1:],
                   duration=frame_ms, loop=0, lossless=True)
    difference = sum(ImageStat.Stat(ImageChops.difference(images[0], images[-1])).mean) / 4
    qa = {'kind': 'character-loop', 'frames': len(images), 'width': spec['width'], 'height': spec['height'],
          'duration': len(images)*frame_ms/1000, 'fps': 1000/frame_ms, 'distinct_poses': len(set(hashes)),
          'first_last_difference': round(difference, 3), 'quality_review': 'pending',
          'review_items': ['首尾动作是否连续', '角色身份与锚点是否一致', '边缘、内部绿色和透明区域是否完整'],
          'note': '按输入姿势组帧，不推断中间肢体；GIF 透明度为二值，WebP 保留透明渐变。'}
    (dest / 'qa.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**qa, 'gif': 'animation.gif', 'image': 'cover.png', 'webp': 'animation.webp', 'qa': 'qa.json'}


def render_blender(payload, dest, preview=False):
    spec = normalize('blender-previs', payload)
    binary = blender_path()
    if not binary:
        raise RuntimeError('未检测到 Blender。安装官方 Blender 后重试，或设置 AI_VIDEO_BLENDER 指向 blender.exe')
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    if preview:
        spec['duration'] = min(3, spec['duration'])
    config = dest / 'scene-spec.json'
    config.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    from filelock import FileLock
    (ROOT/'manifests').mkdir(exist_ok=True)
    with FileLock(str(ROOT/'manifests/gpu.lock'), timeout=0), (dest / 'blender.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(binary), '--background', '--factory-startup', '--disable-autoexec', '--threads', '6',
                        '--python-exit-code', '1', '--python', str(ROOT/'scripts/blender_previs_scene.py'),
                        '--', str(config), str(dest)], stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=900, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    ffmpeg = ROOT / 'tools/ffmpeg.exe'
    filename = 'sample.mp4' if preview else 'video.mp4'
    subprocess.run([str(ffmpeg), '-y', '-v', 'error', '-framerate', str(spec['fps']), '-i',
                    str(dest/'frames/frame-%05d.png'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-movflags', '+faststart', str(dest/filename)],
                   check=True, timeout=180, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    shutil.copy2(dest/'frames/frame-00001.png', dest/'cover.png')
    qa = {'kind': 'blender-previs', 'width': spec['width'], 'height': spec['height'],
          'frames': max(1, round(spec['duration']*spec['fps'])), 'fps': spec['fps'],
          'duration': round(spec['duration']*spec['fps'])/spec['fps'], 'quality_review': 'pending',
          'review_items': ['空间关系和遮挡', '相机路线与目标构图', '角色走位与碰撞接触'],
          'note': '几何白模预演，不是生成式真人成片；可将视频与角色参考图交给支持参考视频的生成服务。'}
    (dest/'qa.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**qa, 'video': filename, 'image': 'cover.png', 'qa': 'qa.json', 'blend': 'scene.blend'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['code-animation', 'character-loop', 'blender-previs'])
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    request = json.loads((args.directory/'render-request.json').read_text(encoding='utf-8'))
    try:
        if args.kind == 'code-animation':
            import code_animation
            result = code_animation.render(request['payload'], args.directory, preview=request['preview'])
        else:
            renderer = render_loop if args.kind == 'character-loop' else render_blender
            result = renderer(request['payload'], args.directory, preview=request['preview'])
        (args.directory/'render-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        (args.directory/'failure.json').write_text(json.dumps({'error': str(exc)}, ensure_ascii=False), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()

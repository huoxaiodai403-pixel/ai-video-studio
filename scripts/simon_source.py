"""Validate the redistributable, patched Simon runtime without Git or network."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = '3ad0a25127c17da48a0e869c9efbf4136c40848b'
REPOSITORY = 'https://github.com/huoxaiodai403-pixel/simon-skills'
WHITEBOARD = 'skills/whiteboard-video/'
EXAMPLE = WHITEBOARD + 'examples/2026-09-08 为什么懂很多道理还是没变化/assets/'
FILES = ('LICENSE', *(WHITEBOARD + name for name in (
    'package.json', 'package-lock.json', 'config.json', 'lib/captions.cjs',
    'lib/paths.cjs', 'lib/render.js', 'lib/render.html', 'lib/scene-dsl.js',
    'assets/fonts/OFL.txt', 'assets/fonts/Xiaolai-Regular.ttf')),
    *(EXAMPLE + name + '.png' for name in ('reader', 'stepper', 'stuck', 'panicked')))


def validate_bundle(root=ROOT):
    root = Path(root).resolve()
    bundle = root / 'apps/simon-skills'
    manifest_path = bundle / 'SOURCE-MANIFEST.json'
    if bundle.is_symlink() or not bundle.resolve().is_relative_to(root) or manifest_path.is_symlink():
        raise ValueError('Simon source bundle must be a real directory inside the workbench.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('repository') != REPOSITORY or manifest.get('revision') != REVISION:
        raise ValueError('Simon source revision does not match the tested fork revision.')
    patch = root / 'workflows/simon-windows.patch'
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest.get('patch_sha256'):
        raise ValueError('Simon Windows patch does not match the bundled source.')
    records = manifest.get('files', {})
    if set(records) != set(FILES):
        raise ValueError('Simon source manifest has missing or unexpected files.')
    paths = [manifest_path]
    for name in FILES:
        path = bundle / name
        if path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('Simon source path must stay inside its bundle.')
        if hashlib.sha256(path.read_bytes()).hexdigest() != records[name]:
            raise ValueError('Simon source checksum mismatch: ' + name)
        paths.append(path)
    return paths


if __name__ == '__main__':
    try:
        files = validate_bundle()
        print(json.dumps({'ready': True, 'repository': REPOSITORY,
                          'revision': REVISION, 'files': len(files)}, ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(json.dumps({'ready': False, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)

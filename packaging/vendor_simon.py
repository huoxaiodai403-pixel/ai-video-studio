"""Maintainer command: import only the pinned public runtime from a Simon checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from simon_source import FILES, REPOSITORY, REVISION, validate_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    args = parser.parse_args()
    destination = ROOT / 'apps/simon-skills'
    if destination.exists():
        raise ValueError('Destination already exists; preserve it before importing a new version.')
    patch = ROOT / 'workflows/simon-windows.patch'
    with tempfile.TemporaryDirectory(prefix='ai-video-simon-import-') as temporary:
        stage = Path(temporary)
        for name in FILES:
            data = subprocess.check_output(['git', '-C', str(args.checkout), 'show', REVISION + ':' + name])
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        subprocess.run(['git', '-C', str(stage), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(stage), 'apply', '--check', str(patch)], check=True)
        subprocess.run(['git', '-C', str(stage), 'apply', str(patch)], check=True)
        manifest = {'repository': REPOSITORY, 'upstream': 'https://github.com/trustfuture/simon-skills',
                    'revision': REVISION, 'license': 'MIT', 'font_license': 'SIL OFL 1.1',
                    'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(), 'files': {}}
        for name in FILES:
            source, target = stage / name, destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            manifest['files'][name] = hashlib.sha256(target.read_bytes()).hexdigest()
        (destination / 'SOURCE-MANIFEST.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Verified bundled Simon files:', len(validate_bundle()))


if __name__ == '__main__':
    main()

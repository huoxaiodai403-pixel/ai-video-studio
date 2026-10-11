"""Download an explicitly reviewed pinned model plan and verify every file."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

import requests
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]


def verified(path, row):
    if not path.is_file() or path.stat().st_size != row['bytes']:
        return False
    if row.get('sha256'):
        digest = hashlib.sha256()
    else:
        digest = hashlib.sha1(b'blob '+str(row['bytes']).encode()+b'\0')
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest() == (row.get('sha256') or row['git_blob_sha1'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('plan', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    def fetch(row):
        path = (ROOT/row['target']).resolve()
        if not path.is_relative_to((ROOT/'models').resolve()):
            raise ValueError('Model plan destination is outside models')
        url = urlparse(row['url'])
        if url.scheme != 'https' or url.hostname != 'huggingface.co' or plan['revision'] not in url.path.split('/'):
            raise ValueError('Expected a pinned public Hugging Face model URL')
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path)+'.download.lock', timeout=0):
            if path.exists():
                if not verified(path, row):
                    raise ValueError('Existing model differs from plan; preserved: '+str(path))
                return {'file': row['name'], 'verified': True, 'reused': True}
            if row['bytes'] >= 64*1024*1024 and row.get('sha256'):
                with path.with_name(path.name+'.download.log').open('w', encoding='utf-8') as log:
                    subprocess.run([sys.executable, str(ROOT/'scripts/download_ranges.py'), row['url'], str(path)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            else:
                response = requests.get(row['url'], timeout=(30,120))
                response.raise_for_status()
                temporary = path.with_name(path.name+'.downloading')
                temporary.write_bytes(response.content)
                if not verified(temporary, row):
                    raise ValueError('Downloaded model data does not match reviewed plan: '+row['name'])
                os.replace(temporary, path)
            if not verified(path, row):
                raise ValueError('Model integrity validation failed: '+row['name'])
            print('VERIFIED '+row['name'], flush=True)
            return {'file': row['name'], 'verified': True, 'bytes': row['bytes'],
                    'sha256': row.get('sha256'), 'git_blob_sha1': row.get('git_blob_sha1')}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetch, plan['files']))
    report = {'repo': plan['repo'], 'revision': plan['revision'], 'files': results, 'all_verified': True}
    args.plan.with_suffix('.verified.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ALL VERIFIED '+plan['repo'], flush=True)


if __name__ == '__main__':
    main()

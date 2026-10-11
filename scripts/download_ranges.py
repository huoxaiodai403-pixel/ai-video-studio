"""Resume a known partial artifact using checked HTTP ranges and SHA-256."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import time
from pathlib import Path
import requests
from urllib.parse import urldefrag, parse_qs


def main():
    p = argparse.ArgumentParser()
    p.add_argument('url')
    p.add_argument('output', type=Path)
    args = p.parse_args()
    output = args.output
    parts = output.with_name(output.name + '.parts')
    parts.mkdir(exist_ok=True)
    args.url, fragment = urldefrag(args.url)
    response = requests.head(args.url, allow_redirects=False, timeout=30)
    response.raise_for_status()
    size = int(response.headers.get('x-linked-size') or response.headers['Content-Length'])
    sha = response.headers.get('x-linked-etag', parse_qs(fragment).get('sha256', [''])[0]).strip('"')
    if len(sha) != 64:
        raise RuntimeError('Expected a SHA-256 LFS digest')
    prefix = parts / 'prefix.bin'
    if output.exists() and not prefix.exists():
        output.rename(prefix)
    initial = prefix.stat().st_size if prefix.exists() else 0
    plan = {'url': args.url, 'size': size, 'sha256': sha, 'prefix_bytes': initial}
    (parts / 'manifest.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    ranges = [(a, min(a+64*1024*1024, size)) for a in range(initial, size, 64*1024*1024)]
    def fetch(bounds):
        start, stop = bounds
        path = parts / f'{start:016}.bin'
        if path.exists() and path.stat().st_size == stop-start:
            return path
        for attempt in range(6):
            try:
                with requests.get(args.url, headers={'Range': f'bytes={start}-{stop-1}'}, stream=True, timeout=(30,90)) as r:
                    r.raise_for_status()
                    if r.status_code != 206 or r.headers.get('Content-Range') != f'bytes {start}-{stop-1}/{size}':
                        raise RuntimeError('Range response mismatch')
                    with path.open('wb') as f:
                        for block in r.iter_content(1024*1024):
                            f.write(block)
                if path.stat().st_size != stop-start:
                    raise RuntimeError('Incomplete range')
                return path
            except (requests.RequestException, RuntimeError):
                if attempt == 5:
                    raise
                time.sleep(min(2**attempt, 20))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        done = 0
        for _ in pool.map(fetch, ranges):
            done += 1
            print(f'{output.name}: {done}/{len(ranges)} ranges complete', flush=True)
    digest = hashlib.sha256()
    temporary = output.with_name(output.name + '.assembling')
    with temporary.open('wb') as dst:
        for source in ([prefix] if prefix.exists() else []) + [parts/f'{a:016}.bin' for a,b in ranges]:
            with source.open('rb') as src:
                for block in iter(lambda: src.read(8*1024*1024), b''):
                    digest.update(block)
                    dst.write(block)
    if temporary.stat().st_size != size or digest.hexdigest() != sha:
        raise RuntimeError('SHA-256 validation failed; parts retained')
    os.replace(temporary, output)
    output.with_name(output.name+'.verified.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    print(f'VERIFIED {output.name} {sha}', flush=True)


if __name__ == '__main__':
    main()

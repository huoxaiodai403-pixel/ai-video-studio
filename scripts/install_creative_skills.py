"""Install pinned article-source files only; never execute upstream setup scripts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/ai-video-studio/scripts'))
from creative_video import blob_sha, catalog, source_path, verify_sources


def git(args, cwd, input_text=None):
    return subprocess.run(['git', *args], cwd=cwd, input=input_text, text=True,
                          encoding='utf-8', check=True, capture_output=True,
                          timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def install(item, root=ROOT):
    base = Path(root) / 'tools/creative-skills'
    base.mkdir(parents=True, exist_ok=True)
    target = source_path(base, item['id'])
    if target.exists():
        check = verify_sources(root, item)
        if check['status'] != 'verified':
            raise ValueError('已有资料版本不符或不完整，已保留：' + str(target))
        return {'id': item['id'], 'status': 'verified_existing', 'files': len(item['files'])}
    with tempfile.TemporaryDirectory(prefix='.creative-source-', dir=base) as temp:
        checkout = Path(temp) / 'checkout'
        checkout.mkdir()
        git(['init', '-q'], checkout)
        git(['remote', 'add', 'origin', 'https://github.com/' + item['repo'] + '.git'], checkout)
        git(['-c', 'credential.interactive=never', 'fetch', '--depth=1', '--filter=blob:none', 'origin', item['ref']], checkout)
        # Exact, validated paths exclude example media, voice assets and setup scripts.
        for relative in item['files']:
            source_path(checkout, relative)
        git(['sparse-checkout', 'set', '--no-cone', '--stdin'], checkout,
            ''.join('/' + relative + '\n' for relative in item['files']))
        git(['-c', 'core.autocrlf=false', 'checkout', '--detach', 'FETCH_HEAD'], checkout)
        if git(['rev-parse', 'HEAD'], checkout).stdout.strip() != item['ref']:
            raise ValueError('上游提交与固定版本不一致')
        stage = Path(temp) / 'ready'
        stage.mkdir()
        for relative, expected in item['files'].items():
            origin = source_path(checkout, relative)
            data = origin.read_bytes()
            if blob_sha(data) != expected:
                raise ValueError('上游文件校验不符：' + relative)
            destination = source_path(stage, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (stage / '.studio-source.json').write_text(json.dumps({
            'repo': item['repo'], 'ref': item['ref'], 'files': item['files'],
            'purpose': 'creative-reference-and-reviewed-chart-code',
            'upstream_setup_executed': False}, ensure_ascii=False, indent=2), encoding='utf-8')
        # Same-volume rename leaves either a complete pack or no installed pack.
        if target.exists():
            raise ValueError('目标在安装时被创建，已保留：' + str(target))
        stage.rename(target)
    return {'id': item['id'], 'status': 'installed', 'files': len(item['files'])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', action='append', help='Select a method ID; repeat; omitted installs all source packs')
    args = parser.parse_args(argv)
    items = catalog()['skills']
    if args.skill:
        unknown = set(args.skill) - {item['id'] for item in items}
        if unknown:
            raise ValueError('未知创作方法：' + ', '.join(sorted(unknown)))
        items = [item for item in items if item['id'] in args.skill]
    for item in items:
        print(json.dumps(install(item), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Article-derived creative methods, pinned source checks and studio handoff.

This helper does not start providers, install models or submit paid jobs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

from studio_client import StudioError, find_root, load_payload, output

MANIFEST = Path(__file__).resolve().parents[1] / 'references/creative-sources.json'
PRODUCTION = Path(__file__).resolve().parents[1] / 'references/creative-production-catalog.json'


def catalog():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def recipe(identity):
    for item in catalog()['skills']:
        if item['id'] == identity:
            return item
    raise ValueError('未知创作方法：' + str(identity))


def source_path(base, relative):
    path = PurePosixPath(relative)
    if (not relative or path.is_absolute() or '..' in path.parts
            or any(c in relative for c in '\\:*?[]\n\r\x00')):
        raise ValueError('非法上游相对路径')
    candidate = Path(base).joinpath(*path.parts)
    for node in (candidate, *candidate.parents):
        if node.is_symlink() or getattr(node, 'is_junction', lambda: False)():
            raise ValueError('上游资料路径不能经过链接：' + str(node))
    if not candidate.resolve().is_relative_to(Path(base).resolve()):
        raise ValueError('上游资料路径越界')
    return candidate


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def verify_sources(root, item):
    base = Path(root) / 'tools/creative-skills' / item['id']
    missing, changed = [], []
    for relative, expected in item['files'].items():
        path = source_path(base, relative)
        if not path.is_file():
            missing.append(relative)
        elif path.stat().st_size > 2_000_000 or blob_sha(path.read_bytes()) != expected:
            changed.append(relative)
    return {'id': item['id'], 'repo': item['repo'], 'ref': item['ref'],
            'status': 'changed' if changed else 'missing' if missing else 'verified',
            'missing': missing, 'changed': changed, 'directory': str(base)}


def prepare_plan(item, payload):
    allowed = {'title', 'route', 'brief', 'style', 'character', 'voice_id',
               'speech_backend', 'image_backend', 'shots', 'production', 'cast'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('仅接受新计划的创作字段；已有计划请用工作台的 revision 保存流程')
    plan = copy.deepcopy(payload)
    if item['id'] != 'simon-skills':
        plan['method_id'] = item['id']
    if not isinstance(plan.get('title'), str) or not plan['title'].strip():
        raise ValueError('请提供作品 title')
    routes = {'code-animation', 'character-story', 'character-loop', 'blender-previs', 'whiteboard', 'knowledge-film'}
    plan.setdefault('route', item['route'])
    if plan['route'] not in routes:
        raise ValueError('未知工作台路线')
    brief = plan.get('brief', '')
    if not isinstance(brief, str):
        raise ValueError('brief 必须为文本')
    plan['brief'] = (brief.rstrip() + '\n\n创作方法：' + item['title'] + '\n'
                     + item['guidance']).lstrip()
    if len(plan['brief']) > 12000:
        raise ValueError('加入创作方法后 brief 超过 12000 字，请精简原始要求')
    plan.setdefault('speech_backend', 'windows')
    plan.setdefault('image_backend', 'online')
    plan.setdefault('shots', [])
    if not isinstance(plan['shots'], list):
        raise ValueError('shots 必须为列表')
    return plan


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, help='Studio root; otherwise discover from the current directory')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List adapted methods without requiring installed upstream sources')
    verify = commands.add_parser('verify', help='Read-only comparison against pinned upstream Git blob hashes')
    verify.add_argument('--recipe')
    prepare = commands.add_parser('prepare', help='Create a fresh studio plan and source record; no generation')
    prepare.add_argument('--recipe', required=True)
    prepare.add_argument('--json', dest='json_file', required=True)
    prepare.add_argument('--out', type=Path, required=True)
    chart = commands.add_parser('chart', help='Compile a Huashu chart spec to the existing code-animation request')
    chart.add_argument('--spec', required=True)
    chart.add_argument('--plan', required=True)
    chart.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'list':
        production = {row['id']: row for row in load_payload(PRODUCTION)['methods']}
        output([{**{k: row[k] for k in ('id', 'title', 'route', 'kind', 'guidance', 'boundary', 'ref')},
                 'local_production': production.get(row['id'])}
                for row in catalog()['skills']])
        return 0
    if args.command == 'prepare':
        item = recipe(args.recipe)
        payload = load_payload(args.json_file)
        plan = prepare_plan(item, payload)
        # A new directory prevents overwriting any user's draft or source notes.
        args.out.mkdir(parents=True, exist_ok=False)
        write_json(args.out / 'generation-plan.json', plan)
        write_json(args.out / 'source-record.json', {'article': catalog()['article'],
                   'method': item['id'], 'repo': item['repo'], 'ref': item['ref'],
                   'boundary': item['boundary'],
                   'input_sha256': hashlib.sha256(Path(args.json_file).read_bytes()).hexdigest(),
                   'status': 'draft', 'media_review': 'not_generated'})
        output({'plan': str((args.out / 'generation-plan.json').resolve()),
                'next': 'studio_client.py submit generation-plan --json <plan>',
                'boundary': item['boundary']})
        return 0
    root = args.root or find_root()
    if root is None or not (root / 'scripts/studio.py').is_file():
        raise ValueError('找不到工作台；请用 doctor 确认路径后传入 --root')
    if args.command == 'verify':
        items = [recipe(args.recipe)] if args.recipe else catalog()['skills']
        checks = [verify_sources(root, item) for item in items]
        output(checks)
        return 0 if all(x['status'] == 'verified' for x in checks) else 1
    if not re.fullmatch(r'gen-[a-f0-9]{32}', args.plan):
        raise ValueError('计划 ID 无效')
    from huashu_chart import compile_chart
    payload = compile_chart(root, load_payload(args.spec))
    write_json(args.out, {'plan_id': args.plan, 'kind': 'code-animation', 'preview': False, 'payload': payload})
    output({'request': str(args.out.resolve()), 'next': 'studio_client.py submit generation-render --json <request>',
            'audio': 'silent' if 'audio_path' not in payload else 'provided', 'quality_review': 'pending'})
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, StudioError) as error:
        output({'error': str(error)}, stream=sys.stderr)
        raise SystemExit(1)

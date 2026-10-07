#!/usr/bin/env python3
"""Portable, standard-library-only client for the local AI Video Studio API."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

JSON_LIMIT = 8 * 1024 * 1024
REQUEST_LIMIT = 500_000
ACTIONS = {
    'whiteboard-preview': '/api/whiteboard/preview',
    'whiteboard-render': '/api/whiteboard/render',
    'investigation-save': '/api/investigation/save',
    'investigation-preview': '/api/investigation/preview',
    'investigation-render': '/api/investigation/render',
    'investigation-resume': '/api/investigation/resume',
    'investigation-media': '/api/investigation/media',
    'source': '/api/investigation/source',
    'speech': '/api/speech',
    'music': '/api/music',
    'image': '/api/generate',
    'motion': '/api/motion',
    'transcribe': '/api/transcribe',
    'produce': '/api/produce',
}
JOB_PATTERN = r'(?:[a-f0-9]{12}|(?:whiteboard|investigation|speech|music|motion|asr|video|enhance|story)-[a-f0-9]{10})'
LIB_PATTERN = r'lib-[a-f0-9]{24}'
PROJECT_PATTERN = r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}'
DOWNLOAD_FIELDS = ('video', 'audio', 'subtitle', 'bundle', 'image', 'storyboard_url',
                   'manifest_url', 'verification', 'metadata', 'transcript', 'manuscript',
                   'source_ledger', 'publish_copy')


class StudioError(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StudioError('工作台请求发生重定向，已停止；请核对服务地址。')


def local_base(value):
    parsed = urlsplit(value)
    try:
        is_loopback = ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        is_loopback = parsed.hostname == 'localhost'
    if (parsed.scheme not in ('http', 'https') or not is_loopback or parsed.username
            or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or '\\' in value or any(ord(c) < 33 for c in value)):
        raise StudioError('服务地址必须是无账号、路径或查询参数的本机 HTTP(S) 地址。')
    try:
        parsed.port
    except ValueError as exc:
        raise StudioError('服务端口无效。') from exc
    return value.rstrip('/')


def identifier(value, pattern, label):
    if not re.fullmatch(pattern, value or ''):
        raise StudioError(label + ' 格式无效。')
    return value


def find_root():
    specified = os.environ.get('AI_VIDEO_STUDIO_ROOT')
    candidates = [Path(specified).expanduser()] if specified else []
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        candidates.extend([start, *start.parents])
    for candidate in candidates:
        if (candidate / 'scripts/studio.py').is_file():
            return candidate.resolve()
    return None


def output(value, stream=sys.stdout):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), file=stream)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StudioError('JSON 含重复字段：' + key)
        result[key] = value
    return result


def load_payload(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > REQUEST_LIMIT:
        raise StudioError('请求 JSON 必须为不超过 500 KB 的现有文件。')
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=strict_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeError) as exc:
        raise StudioError('请求不是有效 UTF-8 JSON：' + str(exc)) from exc
    if not isinstance(data, dict):
        raise StudioError('请求 JSON 顶层必须是对象。')
    return data


class Client:
    def __init__(self, base, timeout=20):
        self.base = local_base(base)
        self.timeout = timeout
        # Local requests must not leave the machine through an environment proxy.
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def open(self, path, data=None):
        if not path.startswith('/') or path.startswith('//'):
            raise StudioError('API 路径无效。')
        body = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if body is not None and len(body) > REQUEST_LIMIT:
            raise StudioError('编码后的请求超过 500 KB。')
        request = Request(self.base + path, data=body,
                          headers={'Content-Type': 'application/json', 'Accept': '*/*'},
                          method='POST' if body is not None else 'GET')
        try:
            return self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            raw = exc.read(JSON_LIMIT + 1)
            try:
                detail = json.loads(raw) if len(raw) <= JSON_LIMIT else None
            except (ValueError, UnicodeError):
                detail = None
            # Preserve job_id and gaps on 422 rather than silently resubmitting.
            raise StudioError(f'工作台返回 HTTP {exc.code}。', detail) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise StudioError('无法连接本机工作台：' + str(exc)) from exc

    def json(self, path, data=None):
        with self.open(path, data) as response:
            raw = response.read(JSON_LIMIT + 1)
        if len(raw) > JSON_LIMIT:
            raise StudioError('API JSON 响应超过 8 MB。')
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise StudioError('工作台没有返回有效 JSON。') from exc

    def job(self, job_id):
        identifier(job_id, JOB_PATTERN, '任务 ID')
        jobs = self.json('/api/jobs')
        if not isinstance(jobs, dict) or job_id not in jobs:
            raise StudioError('任务不存在：' + job_id)
        return {'job_id': job_id, **jobs[job_id]}

    def item(self, item_id):
        identifier(item_id, LIB_PATTERN, '作品 ID')
        return self.json('/api/library/item?' + urlencode({'id': item_id}))['item']


def download_path(value):
    if not isinstance(value, str):
        raise StudioError('所选交付文件尚未生成。')
    parsed = urlsplit(value)
    decoded = unquote(parsed.path)
    if parsed.scheme or parsed.netloc or parsed.fragment or '\\' in decoded or any(ord(c) < 32 for c in decoded):
        raise StudioError('下载地址必须是工作台返回的本机交付路径。')
    if any(part in ('.', '..') for part in decoded.split('/')):
        raise StudioError('下载路径含无效跳转段。')
    if decoded.startswith('/outputs/') and not parsed.query:
        pieces = decoded.split('/')
        identifier(pieces[2] if len(pieces) > 3 else '', JOB_PATTERN, '交付任务 ID')
        return value
    if decoded == '/api/library/file':
        query = parse_qs(parsed.query)
        if set(query) == {'id'} and len(query['id']) == 1:
            identifier(query['id'][0], LIB_PATTERN, '作品 ID')
            return value
    raise StudioError('仅能下载作品目录或任务输出文件。')


def save_download(client, path, destination, max_bytes):
    path = download_path(path)
    destination = Path(destination).expanduser().absolute()
    if destination.exists():
        raise StudioError('目标文件已存在，请另选文件名：' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting even if the destination appears mid-request.
    created = False
    try:
        with client.open(path) as response:
            declared = response.headers.get('Content-Length')
            if declared is not None and int(declared) > max_bytes:
                raise StudioError('交付文件超过下载大小上限。')
            digest, count = hashlib.sha256(), 0
            with destination.open('xb') as stream:
                created = True
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > max_bytes:
                        raise StudioError('交付文件超过下载大小上限。')
                    digest.update(chunk)
                    stream.write(chunk)
            if not count or (declared is not None and count != int(declared)):
                raise StudioError('交付文件为空或未下载完整。')
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {'file': str(destination), 'bytes': count, 'sha256': digest.hexdigest()}


def doctor(client):
    root = find_root()
    checks = {}
    for name, route in (
        ('services', '/api/services'), ('whiteboard', '/api/whiteboard/status'),
        ('qwen_tts', '/api/voice-library/qwen-status'), ('music', '/api/music'),
    ):
        try:
            checks[name] = client.json(route)
        except StudioError as exc:
            checks[name] = {'reachable': False, 'error': str(exc), 'detail': exc.detail}
    try:
        jobs = client.json('/api/jobs')
        service_available = isinstance(jobs, dict)
        active = [{'job_id': key, 'kind': value.get('kind'), 'status': value.get('status'),
                   'phase': value.get('phase')} for key, value in jobs.items()
                  if isinstance(value, dict) and value.get('status') in ('queued', 'running')]
    except StudioError as exc:
        service_available, active = False, []
        checks['jobs'] = {'error': str(exc)}
    return {'url': client.base, 'service_available': service_available,
            'root': str(root) if root else None, 'python': sys.executable,
            'start_script': str(root / 'scripts/Start-Studio.ps1') if root else None,
            'active_jobs': active, 'checks': checks,
            'note': '只读检查；未启动服务、下载模型或执行生成。Codex 写稿无需本地编剧模型。'}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--url', default=os.environ.get('AI_VIDEO_STUDIO_URL', 'http://127.0.0.1:8189'))
    result.add_argument('--timeout', type=float, default=None,
                        help='Request timeout seconds; default 600 for Jianying draft creation, 20 otherwise')
    sub = result.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='Read-only service and dependency checks')
    listing = sub.add_parser('list', help='List unified products or reusable assets')
    listing.add_argument('--view', choices=('products', 'assets'), default='products')
    listing.add_argument('--status', default='done', choices=('all', 'done', 'draft', 'preview', 'queued', 'running', 'error'))
    listing.add_argument('--kind', default='all')
    listing.add_argument('--query', default='')
    listing.add_argument('--favorite', action='store_true')
    sub.add_parser('voices', help='List actual preset IDs and voice configurations')
    sub.add_parser('models', help='Read creation settings/model inventory and music engines')
    item = sub.add_parser('item', help='Read one library item')
    item.add_argument('item_id')
    status = sub.add_parser('status', help='Read job state; optionally wait up to 60 seconds')
    status.add_argument('job_id')
    status.add_argument('--wait', type=float, default=0)
    status.add_argument('--interval', type=float, default=3)
    project = sub.add_parser('project', help='Read saved investigation storyboard, assets and gaps')
    project.add_argument('job_id')
    submit = sub.add_parser('submit', help='Submit a JSON file to a named creation endpoint')
    submit.add_argument('action', choices=tuple(ACTIONS))
    submit.add_argument('--json', required=True, dest='json_file')
    jianying = sub.add_parser('jianying', help='Check, create a local draft, or launch installed Jianying')
    editor = jianying.add_subparsers(dest='editor_action', required=True)
    editor_status = editor.add_parser('status', help='Read installation and optional project handoff status')
    editor_status.add_argument('--project')
    editor_export = editor.add_parser('export', help='Create a new Jianying draft from an existing studio project')
    editor_export.add_argument('--project', required=True)
    editor_export.add_argument('--mode', choices=('auto', 'scenes', 'flattened'), default='auto')
    editor_open = editor.add_parser('open', help='Launch detected Jianying; project selection remains a UI action')
    editor_open.add_argument('--project')
    download = sub.add_parser('download', help='Download a real local delivery without overwriting')
    source = download.add_mutually_exclusive_group(required=True)
    source.add_argument('--job')
    source.add_argument('--item')
    which = download.add_mutually_exclusive_group()
    which.add_argument('--field', choices=DOWNLOAD_FIELDS)
    which.add_argument('--label', help='Exact label from the job downloads array')
    download.add_argument('--output', required=True)
    download.add_argument('--max-mb', type=int, default=4096)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    draft_creation = args.command == 'jianying' and args.editor_action == 'export'
    timeout_limit = 600 if draft_creation else 60
    timeout = args.timeout if args.timeout is not None else (600 if draft_creation else 20)
    if not 0 < timeout <= timeout_limit:
        raise StudioError(f'请求超时应大于 0 且不超过 {timeout_limit} 秒。')
    client = Client(args.url, timeout)
    if args.command == 'doctor':
        result = doctor(client)
        output(result)
        return 0 if result['service_available'] else 1
    if args.command == 'list':
        query = {'view': args.view, 'status': args.status, 'kind': args.kind, 'q': args.query}
        if args.favorite:
            query['favorite'] = '1'
        result = client.json('/api/library?' + urlencode(query))
    elif args.command == 'voices':
        result = client.json('/api/voice-library')
    elif args.command == 'models':
        result = {'creation': client.json('/api/creation'), 'music': client.json('/api/music')}
    elif args.command == 'item':
        result = client.item(args.item_id)
    elif args.command == 'project':
        identifier(args.job_id, r'investigation-[a-f0-9]{10}', '长片工程 ID')
        result = client.json('/api/investigation/project?' + urlencode({'job_id': args.job_id}))
    elif args.command == 'status':
        if not 0 <= args.wait <= 60 or not 1 <= args.interval <= 30:
            raise StudioError('单次等待应为 0–60 秒，轮询间隔为 1–30 秒。')
        deadline = time.monotonic() + args.wait
        while True:
            result = client.job(args.job_id)
            remaining = deadline - time.monotonic()
            if result.get('status') not in ('queued', 'running') or remaining <= 0:
                break
            time.sleep(min(args.interval, remaining))
    elif args.command == 'submit':
        payload = load_payload(args.json_file)
        if args.action in ('speech', 'image', 'motion', 'transcribe') and payload.get('backend') != 'local':
            raise StudioError('此分享客户端单项生成要求显式 backend=local，在线提供商请在工作台中按用户选择操作。')
        if args.action == 'produce' and any(value != 'local' for value in payload.get('storyboard', {}).get('backends', {}).values()):
            raise StudioError('此分享客户端不提交在线流水线。')
        result = client.json(ACTIONS[args.action], payload)
    elif args.command == 'jianying':
        project_id = identifier(args.project, PROJECT_PATTERN, '工程 ID') if args.project else None
        if args.editor_action == 'status':
            query = '?' + urlencode({'project_id': project_id}) if project_id else ''
            result = client.json('/api/jianying/status' + query)
        else:
            payload = {'project_id': project_id} if project_id else {}
            if args.editor_action == 'export':
                payload['mode'] = args.mode
            result = client.json('/api/jianying/' + args.editor_action, payload)
    elif args.command == 'download':
        if not 1 <= args.max_mb <= 16384:
            raise StudioError('下载上限应为 1–16384 MB。')
        if args.item:
            if args.field or args.label:
                raise StudioError('按作品 ID 下载主文件时不使用 --field 或 --label。')
            item = client.item(args.item)
            path = item.get('download_url')
        else:
            if not args.field and not args.label:
                raise StudioError('按任务下载需要 --field 或 --label。')
            job = client.job(args.job)
            if args.field:
                path = job.get(args.field)
            else:
                rows = [row for row in job.get('downloads', []) if row.get('label') == args.label]
                if len(rows) != 1:
                    raise StudioError('交付标签不存在或不唯一，请先读取任务状态。')
                path = rows[0].get('url')
        result = save_download(client, path, args.output, args.max_mb * 1024 * 1024)
    else:
        raise StudioError('未知命令。')
    output(result)
    return 0


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except (StudioError, OSError, ValueError, KeyError, TypeError) as error:
        output({'error': str(error), 'detail': getattr(error, 'detail', None)}, sys.stderr)
        sys.exit(1)

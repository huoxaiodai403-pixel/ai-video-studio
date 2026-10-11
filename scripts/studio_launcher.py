"""Start this checkout and verify its identity before opening a browser."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]


def runtime_at(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/api/runtime', timeout=1) as response:
            value = json.loads(response.read(65536))
        return value if isinstance(value, dict) else None
    except (OSError, URLError, ValueError):
        return None


def same_workbench(value, root):
    return (isinstance(value, dict) and isinstance(value.get('root'), str)
            and isinstance(value.get('python'), str) and bool(value.get('version'))
            and Path(value['root']).resolve() == Path(root).resolve())


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.25)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def ensure_started(root=ROOT, port=8189, timeout=30):
    root = Path(root).resolve()
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError('Port must be 1024-65535.')
    for folder in ('logs', 'manifests'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    url = f'http://127.0.0.1:{port}/home'
    with FileLock(str(root / 'manifests/studio-launch.lock'), timeout=timeout):
        endpoint_file = root / 'manifests/studio-endpoint.json'
        try:
            saved_port = json.loads(endpoint_file.read_text('utf-8'))['port']
        except (OSError, ValueError, KeyError, TypeError):
            saved_port = port
        if (isinstance(saved_port, int) and not isinstance(saved_port, bool) and 1024 <= saved_port <= 65535
                and saved_port != port and same_workbench(runtime_at(saved_port), root)):
            raise RuntimeError(f'This workbench is already running on port {saved_port}. '
                               f'Use Start.cmd -Port {saved_port}; two servers must not write to the same projects.')
        current = runtime_at(port)
        if same_workbench(current, root):
            return {'url': url, 'root': str(root), 'already_running': True}
        if current or listening(port):
            owner = current.get('root', 'another application') if current else 'another application'
            raise RuntimeError(f'Port {port} belongs to {owner}. Nothing was stopped. '
                               'Choose an unused port with Start.cmd -Port <port> or close that application yourself.')
        python = root / 'tools/.venv/Scripts/python.exe'
        if not python.is_file():
            raise RuntimeError('Run Install.cmd in this folder first; copied virtual environments must be reinstalled.')
        out = root / 'logs/studio.out.log'
        err = root / 'logs/studio.err.log'
        with out.open('w', encoding='utf-8') as stdout, err.open('w', encoding='utf-8') as stderr:
            process = subprocess.Popen([str(python), '-X', 'utf8', str(root / 'scripts/studio.py'), '--port', str(port)],
                                       cwd=root, stdout=stdout, stderr=stderr,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'manifests/studio.pid').write_text(str(process.pid), encoding='ascii')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Workbench exited ({process.returncode}). See {err}; rerun Install.cmd if dependencies are missing.')
            if same_workbench(runtime_at(port), root):
                endpoint_file.write_text(json.dumps({'port': port, 'pid': process.pid}), encoding='utf-8')
                return {'url': url, 'root': str(root), 'pid': process.pid, 'already_running': False}
            time.sleep(.25)
        raise RuntimeError(f'Workbench did not become ready. See {err}. No other process was stopped.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8189)
    args = parser.parse_args()
    try:
        print(json.dumps(ensure_started(port=args.port), ensure_ascii=False))
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

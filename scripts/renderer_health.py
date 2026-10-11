"""Inspect installed CPU modules, not just their package.json placeholder files."""
import functools
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


@functools.lru_cache(maxsize=8)
def _inspect(root, animation, bucket):
    root = Path(root)
    node = root / 'tools/node/node.exe'
    ffmpeg = root / 'tools/ffmpeg.exe'
    if not node.is_file() or not ffmpeg.is_file():
        return {'ready': False, 'message': '请安装 CPU 渲染组件；缺少工作台 Node 或 FFmpeg。'}
    env = os.environ.copy()
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(root / 'cache/ms-playwright')
    command = [str(node), str(root / 'scripts/check_renderers.cjs'), '--inspect']
    if animation:
        command.append('--animation')
    try:
        result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            return {'ready': False, 'message': '渲染依赖不完整或无法载入，请检查安装日志与安全软件隔离记录；确认后再修复安装。',
                    'detail': result.stderr[-1800:]}
        value = json.loads(result.stdout)
        if value.get('ready') is not True:
            raise ValueError('renderer did not confirm readiness')
        return {**value, 'message': 'CPU 渲染依赖已载入；成片仍需实际渲染验证。'}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {'ready': False, 'message': '渲染依赖检查未完成，请查看安装日志。', 'detail': str(exc)}


def inspect(root=ROOT, *, animation=False):
    return dict(_inspect(str(Path(root).resolve()), animation, int(time.monotonic() // 15)))

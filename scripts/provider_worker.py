"""Enter a request-scoped provider context before loading an isolated worker."""
import json
import runpy
import sys
from pathlib import Path

import providers


def main():
    raw = sys.stdin.buffer.read(1024*1024+1)
    try:
        if len(raw) > 1024*1024:
            raise ValueError()
        snapshot = json.loads(raw)
        if (not isinstance(snapshot, dict) or set(snapshot) - set(providers.SNAPSHOT_KINDS)
                or any(not isinstance(row, dict) for row in snapshot.values())):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError('本次在线服务配置传递失败，未开始制作。') from None
    if len(sys.argv) < 2:
        raise ValueError('Missing worker entry point')
    target = Path(sys.argv[1]).resolve()
    # This private entry point runs repository workers, never a request-supplied
    # script or arbitrary media file. Worker arguments retain their own checks.
    if target.parent != Path(__file__).resolve().parent or target.suffix != '.py' or not target.is_file():
        raise ValueError('Invalid worker entry point')
    sys.argv = [str(target), *sys.argv[2:]]
    with providers.frozen(snapshot):
        runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main()

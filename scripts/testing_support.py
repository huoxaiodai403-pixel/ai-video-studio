"""Test-owned temp folders with bounded Windows delete-pending retries."""
import os
from pathlib import Path
import tempfile
import time


class TemporaryDirectory(tempfile.TemporaryDirectory):
    """Retry only transient Windows directory/sharing errors, never suppress failure.

    Windows can report ERROR_DIR_NOT_EMPTY just after the final child was deleted.
    The next enumeration can already be empty. Keep each retry scoped to this
    object's original test-created directory; unrelated paths are never removed.
    """
    def __init__(self):
        super().__init__(prefix='ai-video-test-')
        self._owned_path = Path(self.name).resolve(strict=True)

    def _check_owned_path(self):
        target = Path(self.name)
        if (target.is_symlink() or target.is_junction() or target.resolve() != self._owned_path
                or target.parent.resolve() != self._owned_path.parent
                or not target.name.startswith('ai-video-test-')):
            raise ValueError('Refusing cleanup outside the originally created test directory')

    def cleanup(self):
        self._check_owned_path()
        delays = (0.02, 0.05, 0.1, 0.2, 0.4)
        for attempt in range(len(delays) + 1):
            try:
                super().cleanup()
                return
            except OSError as error:
                if os.name != 'nt' or getattr(error, 'winerror', None) not in (32, 145):
                    raise
                if attempt == len(delays):
                    try:
                        remaining = [str(path.relative_to(self._owned_path)) for path in self._owned_path.rglob('*')][:20]
                    except OSError as inspect_error:
                        remaining = [str(inspect_error)]
                    error.add_note('Bounded test cleanup retries exhausted; remaining: ' + repr(remaining))
                    raise
                time.sleep(delays[attempt])
                self._check_owned_path()

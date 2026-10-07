"""Content keys for resuming expensive per-scene local speech work."""
import hashlib
import json
from pathlib import Path


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def model_revision(folder):
    folder = Path(folder)
    return {'path': str(folder.resolve()), 'files': [
        [p.name, p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(folder.iterdir()) if p.is_file()]}


def read_cached(metadata, audio, key):
    try:
        saved = json.loads(Path(metadata).read_text(encoding='utf-8'))
        if saved.get('input_sha256') == key and saved.get('audio_sha256') == file_sha(audio):
            return saved
    except (OSError, ValueError):
        pass
    return None

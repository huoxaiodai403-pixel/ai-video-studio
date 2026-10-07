"""Idempotent first-run setup. Never replace user settings or model files."""
import json
from pathlib import Path
import shutil
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def initialize():
    for folder in ('tools', 'logs', 'manifests', 'config', 'projects/studio', 'projects/drafts', 'assets/voices', 'cache'):
        (ROOT/folder).mkdir(parents=True, exist_ok=True)
    ffmpeg = ROOT/'tools/ffmpeg.exe'
    if not ffmpeg.exists():
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg)
    creation = ROOT/'config/creation.json'
    if not creation.exists():
        # A reference-free voice selection lets online tools work before local models are installed.
        creation.write_text(json.dumps({'voice': {'engine': 'qwen3-custom', 'reference': '',
                                                   'qwen_speaker': 'Vivian'}}, indent=2), encoding='utf-8')
    print('Runtime folders ready; existing settings preserved.')


if __name__ == '__main__':
    initialize()

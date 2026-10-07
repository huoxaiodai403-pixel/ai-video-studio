"""Select only the runtime needed by the frozen project, without importing models."""
from pathlib import Path
from creation_settings import voice_for

ROOT = Path(__file__).resolve().parents[1]


def tts_python(spec):
    needs_index = any(voice_for(spec, scene).get('engine', 'index-tts') == 'index-tts'
                      for scene in spec.get('scenes', []))
    return ROOT/('apps/index-tts/.venv/Scripts/python.exe' if needs_index else 'tools/.venv/Scripts/python.exe')

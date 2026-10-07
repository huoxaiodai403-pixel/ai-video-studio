"""Hold the shared GPU lock while a standalone model service is running."""
import os
import subprocess
import sys
import requests
from filelock import FileLock
from prompt_library import ROOT
from comfy_client import unload

if __name__ == '__main__':
    os.environ['PATH']=str(ROOT/'tools')+os.pathsep+os.environ['PATH']
    with FileLock(str(ROOT/'manifests/gpu.lock'),timeout=0):
        try:
            unload()
        except requests.ConnectionError:
            # Standalone voice/ASR tasks also work when ComfyUI is stopped.
            pass
        raise SystemExit(subprocess.call(sys.argv[1:]))

$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8='1'
$env:HF_HUB_DISABLE_TELEMETRY='1'
$env:PATH=(Join-Path $root 'tools')+';'+$env:PATH
Set-Location (Join-Path $root 'apps\index-tts')
& (Join-Path $root 'tools\.venv\Scripts\python.exe') (Join-Path $root 'scripts\with_gpu.py') (Join-Path $root 'apps\index-tts\.venv\Scripts\python.exe') (Join-Path $root 'apps\index-tts\webui.py') --host 127.0.0.1 --port 7860 --fp16

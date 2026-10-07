param([Parameter(Mandatory=$true)][string]$Audio)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8='1'
$env:HF_HOME=Join-Path $root 'cache\huggingface'
$env:HF_HUB_OFFLINE='1'
$env:PATH=(Join-Path $root 'tools')+';'+$env:PATH
& (Join-Path $root 'apps\qwen-asr\.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'transcribe.py') $Audio
if ($LASTEXITCODE -ne 0) { throw 'Transcription failed; see the error above.' }

$ErrorActionPreference='Stop'
$llmRoot=Split-Path $PSScriptRoot -Parent
$llmExe=Join-Path $llmRoot 'apps\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $llmExe)) { throw 'Ollama is not installed in apps\Ollama.' }
if (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) { return }
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_MODELS=Join-Path $llmRoot 'models\ollama'
$env:OLLAMA_CONTEXT_LENGTH='32768'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$env:OLLAMA_KEEP_ALIVE='0'
$env:OLLAMA_NO_CLOUD='1'
$llmProcess=Start-Process -FilePath $llmExe -ArgumentList 'serve' -WorkingDirectory (Split-Path $llmExe) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $llmRoot 'logs\ollama.out.log') -RedirectStandardError (Join-Path $llmRoot 'logs\ollama.err.log') -PassThru
$llmProcess.Id | Set-Content (Join-Path $llmRoot 'manifests\ollama.pid')
Write-Host "Ollama started: PID $($llmProcess.Id)"

[CmdletBinding()]
param([switch]$WorkbenchOnly, [switch]$StartLocalModels, [ValidateRange(1024,65535)][int]$Port=8189)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
$root=Split-Path $PSScriptRoot -Parent
if ($WorkbenchOnly -and $StartLocalModels) { throw 'Choose -WorkbenchOnly or -StartLocalModels, not both.' }
foreach ($folder in @('logs','manifests','config','projects/studio','projects/drafts','assets/voices')) {
    New-Item -ItemType Directory -Path (Join-Path $root $folder) -Force | Out-Null
}
$studioPython=Join-Path $root 'tools/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Run Install.cmd first to install the workbench runtime.' }
$env:PYTHONUTF8='1'
$env:HF_HOME=Join-Path $root 'cache\huggingface'
$env:HF_HUB_DISABLE_TELEMETRY='1'
& $studioPython -X utf8 (Join-Path $PSScriptRoot 'studio_launcher.py') --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Workbench startup failed. See the message above and logs/studio.err.log.' }
function Start-LocalService($Name,$Exe,$Arguments,$Directory,$Port) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { Write-Host "$Name port $Port already in use; not starting another process."; return }
    $existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.ExecutablePath -eq $Exe -and $_.CommandLine -like "*$Arguments*" }
    if ($existing) { Write-Host "$Name is still starting; not starting another process."; return }
    $p=Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root "logs\$Name.out.log") -RedirectStandardError (Join-Path $root "logs\$Name.err.log") -PassThru
    $p.Id | Set-Content (Join-Path $root "manifests\$Name.pid")
    Write-Host "$Name started: PID $($p.Id)"
}
$comfyPython=Join-Path $root 'apps/ComfyUI/.venv/Scripts/python.exe'
if ($StartLocalModels -and (Test-Path -LiteralPath $comfyPython)) {
    Start-LocalService 'comfyui' $comfyPython 'main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch --disable-api-nodes --reserve-vram 2' (Join-Path $root 'apps/ComfyUI') 8188
}
if ($StartLocalModels -and (Test-Path (Join-Path $root 'apps/Ollama/ollama.exe'))) { & (Join-Path $PSScriptRoot 'Start-LLM.ps1') }
Write-Host "Prompt studio: http://127.0.0.1:$Port/home"
if ($StartLocalModels) { Write-Host 'ComfyUI: http://127.0.0.1:8188' }
else { Write-Host 'Local model services are optional. Start them from local settings or use -StartLocalModels.' }

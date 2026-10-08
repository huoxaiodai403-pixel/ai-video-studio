[CmdletBinding()]
param([string]$PythonPath = '', [switch]$InstallJianying, [switch]$NonInteractive)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
$studioRoot = Split-Path $PSScriptRoot -Parent
if (-not $PythonPath) { $PythonPath = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Install the Studio runtime first, or supply -PythonPath.' }
function Get-JianyingStatus {
    $state = & $PythonPath -X utf8 (Join-Path $PSScriptRoot 'jianying_bridge.py') status
    if ($LASTEXITCODE) { throw "Could not inspect Jianying: $state" }
    return ($state | ConvertFrom-Json)
}
$installation = Get-JianyingStatus
if (-not $installation.installed) {
    if (-not $InstallJianying) {
        if ($NonInteractive) { throw 'Jianying is missing. Ask the user first, then rerun with -InstallJianying after consent.' }
        $answer = Read-Host 'Jianying is not installed. Install the official desktop app via winget and configure the bridge? [y/N]'
        if ($answer -notmatch '^(?i:y|yes)$') { Write-Host 'Installation skipped. No app or bridge was installed.'; return }
    }
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'winget is unavailable. Install Jianying from https://www.capcut.cn/, then rerun this script.' }
    & winget.exe install --exact --id ByteDance.JianyingPro --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Jianying installation did not complete ($LASTEXITCODE). Check the installer and rerun; no bridge was configured." }
    $installation = Get-JianyingStatus
    if (-not $installation.installed) { throw 'The installer exited, but JianyingPro.exe was not found. Complete the installation or configure config/jianying.json, then rerun.' }
}
$bridgeRoot = Join-Path $studioRoot 'apps/jianying-bridge'
$bridgePython = Join-Path $bridgeRoot '.venv/Scripts/python.exe'
function Assert-BridgePython([string]$Executable) {
    # Avoid embedded native-argument quotes: Windows PowerShell 5.1 strips them.
    & $Executable -c 'import sys; print(sys.version.split()[0]); sys.exit(0 if sys.version_info.major == 3 and 12 <= sys.version_info.minor <= 14 and sys.maxsize.bit_length() == 63 else 1)'
    if ($LASTEXITCODE) {
        throw 'The pinned Jianying dependencies require 64-bit Python 3.12-3.14. Install Python 3.12 and rerun with -PythonPath pointing to its python.exe. If apps/jianying-bridge/.venv already exists with an older Python, rename that environment as a backup first; do not remove your projects or drafts.'
    }
}
if (-not (Test-Path -LiteralPath $bridgePython)) {
    Assert-BridgePython $PythonPath
    & $PythonPath -m venv (Join-Path $bridgeRoot '.venv')
    if ($LASTEXITCODE) { throw 'Could not create the isolated bridge environment.' }
}
Assert-BridgePython $bridgePython
& $bridgePython -m pip install -r (Join-Path $PSScriptRoot 'requirements-jianying.txt')
if ($LASTEXITCODE) { throw 'Could not install the pinned bridge dependencies.' }
& $bridgePython -X utf8 (Join-Path $PSScriptRoot 'jianying_bridge.py') doctor
if ($LASTEXITCODE) { throw 'Draft writer import validation failed.' }
$installation = Get-JianyingStatus
if (-not $installation.draft_root) {
    Start-Process -FilePath $installation.executable -WindowStyle Hidden | Out-Null
    Write-Host 'Jianying launched for first-run setup. Finish any app prompts, then rerun studio_client.py jianying status.'
    for ($studioAttempt = 0; $studioAttempt -lt 10 -and -not $installation.draft_root; $studioAttempt++) {
        Start-Sleep -Milliseconds 500
        $installation = Get-JianyingStatus
    }
}
if ($installation.bridge_ready -and $installation.draft_root) {
    Write-Host 'Jianying app, draft directory and draft bridge are ready. Draft opening still needs a real handoff check.'
} else {
    Write-Host 'Bridge dependencies installed; waiting for Jianying first-run setup and draft directory discovery.'
}

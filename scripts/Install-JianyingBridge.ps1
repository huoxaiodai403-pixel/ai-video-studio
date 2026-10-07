param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path $PSScriptRoot -Parent
if (-not $PythonPath) { $PythonPath = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Install the Studio runtime first, or supply -PythonPath.' }
$bridgeRoot = Join-Path $studioRoot 'apps/jianying-bridge'
$bridgePython = Join-Path $bridgeRoot '.venv/Scripts/python.exe'
function Assert-BridgePython([string]$Executable) {
    & $Executable -c 'import sys, struct; print("Bridge Python: " + sys.version.split()[0]); sys.exit(0 if sys.version_info.major == 3 and 12 <= sys.version_info.minor <= 14 and struct.calcsize("P") == 8 else 1)'
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
Write-Host 'Jianying draft bridge installed. Install and start Jianying once to discover its draft directory.'

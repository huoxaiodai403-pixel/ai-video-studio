[CmdletBinding()]
param([string]$PythonPath, [switch]$InstallPython, [switch]$Renderers, [switch]$SkipRenderers)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
if ($Renderers -and $SkipRenderers) { throw 'Choose -Renderers or -SkipRenderers, not both.' }
$studioRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8 = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
foreach ($folder in @('tools','logs','manifests','config','projects/studio','projects/drafts','assets/voices','cache')) {
    New-Item -ItemType Directory -Path (Join-Path $studioRoot $folder) -Force | Out-Null
}
function Find-StudioPython {
    $candidates = @($PythonPath, (Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'))
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        foreach ($line in (& py.exe --list-paths 2>$null)) {
            if ($line -match '([A-Za-z]:\\.+python(?:\.exe)?)\s*$') { $candidates += $matches[1].Trim() }
        }
    }
    foreach ($version in @('312','311','313','314')) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs/Python/Python$version/python.exe"
    }
    $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($onPath -and $onPath.Source -notlike '*WindowsApps*') { $candidates += $onPath.Source }
    foreach ($candidate in $candidates) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate)) { continue }
        $versionInfo = & $candidate -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sys.maxsize.bit_length())' 2>$null
        if ($LASTEXITCODE -eq 0 -and $versionInfo -match '^3 (11|12|13|14) 63$') { return $candidate }
    }
    return $null
}
$pythonExe = Find-StudioPython
if (-not $pythonExe -and $InstallPython) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11-3.14 (64-bit) from python.org, then run Install.cmd again. winget was not found.' }
    & winget.exe install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed ($LASTEXITCODE)." }
    $pythonExe = Find-StudioPython
}
if (-not $pythonExe) { throw 'Python 3.11-3.14 (64-bit) is required. Run Install.cmd or supply -PythonPath C:\path\python.exe.' }
$venvPython = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $pythonExe -m venv (Join-Path $studioRoot 'tools/.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
& $venvPython -m pip install --requirement (Join-Path $studioRoot 'requirements-studio.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network and rerun Install.cmd.' }
& $venvPython (Join-Path $PSScriptRoot 'bootstrap_studio.py')
if ($LASTEXITCODE -ne 0) { throw 'Workbench initialization failed.' }
if (-not $SkipRenderers) { & (Join-Path $PSScriptRoot 'Install-Renderers.ps1') }
Write-Host 'Ready. Run Start.cmd. Codex can write storyboards; CPU renderers need no AI model.'
if ($SkipRenderers) { Write-Host 'Renderers skipped. Run scripts/Install-Renderers.ps1 before previewing.' }
Write-Host 'Narration and alignment still need prepared audio/timestamps or an available speech engine.'
Write-Host 'No AI model weights, voice samples, or API credentials have been installed.'

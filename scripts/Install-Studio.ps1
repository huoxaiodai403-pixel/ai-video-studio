[CmdletBinding()]
param([string]$PythonPath, [switch]$InstallPython, [switch]$IsolatedPython, [switch]$Renderers, [switch]$SkipRenderers)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
. (Join-Path $PSScriptRoot 'Studio-Setup.ps1')
if ($Renderers -and $SkipRenderers) { throw 'Choose -Renderers or -SkipRenderers, not both.' }
if ($PythonPath -and $IsolatedPython) { throw 'Choose -PythonPath or -IsolatedPython, not both.' }
$studioRoot = Split-Path $PSScriptRoot -Parent
$runtime = Get-Content -LiteralPath (Join-Path $studioRoot 'runtime-dependencies.json') -Raw | ConvertFrom-Json
$localPython = Join-Path $studioRoot "tools/python-$($runtime.minimum.python_bootstrap.version)/tools/python.exe"
$env:PYTHONUTF8 = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
foreach ($folder in @('tools','logs','manifests','config','projects/studio','projects/drafts','assets/voices','cache')) {
    New-Item -ItemType Directory -Path (Join-Path $studioRoot $folder) -Force | Out-Null
}
function Find-StudioPython {
    if ($PythonPath) {
        if (-not (Test-StudioPython $PythonPath)) { throw 'The supplied -PythonPath is not a working Python 3.11-3.14 x64 installation with venv.' }
        return (Resolve-Path -LiteralPath $PythonPath).Path
    }
    if ($IsolatedPython) { if (Test-StudioPython $localPython) { return $localPython }; return $null }
    $candidates = @((Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'), $localPython)
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        try { $launcherPaths = & py.exe --list-paths 2>$null } catch { $launcherPaths = @() }
        foreach ($line in $launcherPaths) {
            if ($line -match '([A-Za-z]:\\.+python(?:\.exe)?)\s*$') { $candidates += $matches[1].Trim() }
        }
    }
    foreach ($version in @('312','311','313','314')) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs/Python/Python$version/python.exe"
    }
    $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($onPath -and $onPath.Source -notlike '*WindowsApps*') { $candidates += $onPath.Source }
    foreach ($candidate in $candidates) {
        if (Test-StudioPython $candidate) { return $candidate }
    }
    return $null
}
$pythonExe = Find-StudioPython
if (-not $pythonExe -and ($InstallPython -or $IsolatedPython)) {
    $bootstrap = $runtime.minimum.python_bootstrap
    $setupCache = Join-Path $studioRoot 'cache/setup'
    New-Item -ItemType Directory -Path $setupCache -Force | Out-Null
    $archive = Join-Path $setupCache "python-$($bootstrap.version).zip"
    Write-Host "Installing application-local Python $($bootstrap.version) (no winget or administrator required)..."
    Get-StudioArchive $bootstrap.url $bootstrap.sha256 $archive
    $pythonRoot = Split-Path (Split-Path $localPython -Parent) -Parent
    Save-StudioRuntime $pythonRoot $studioRoot
    Expand-Archive -LiteralPath $archive -DestinationPath $pythonRoot
    if (-not (Test-StudioPython $localPython)) { throw 'Downloaded Python cannot run. Check Windows x64 compatibility and security software.' }
    $pythonExe = $localPython
}
if (-not $pythonExe) { throw 'Python 3.11-3.14 (64-bit) is required. Run Install.cmd or supply -PythonPath C:\path\python.exe.' }
$venvPython = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'
$venvReady = Test-StudioPython $venvPython
if ($venvReady -and $IsolatedPython) {
    $venvBase = & $venvPython -I -c 'import sys; print(sys._base_executable)'
    $venvReady = ($LASTEXITCODE -eq 0 -and [IO.Path]::GetFullPath($venvBase.Trim()) -eq [IO.Path]::GetFullPath($localPython))
}
if (-not $venvReady) {
    Save-StudioRuntime (Join-Path $studioRoot 'tools/.venv') $studioRoot
    & $pythonExe -m venv (Join-Path $studioRoot 'tools/.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
Write-Host 'Installing isolated web/media dependencies...'
& $venvPython -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'pip could not be initialized. Check the Python runtime and installation logs.' }
& $venvPython -m pip install --only-binary=:all: --requirement (Join-Path $studioRoot 'requirements-studio.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network and rerun Install.cmd.' }
& $venvPython (Join-Path $PSScriptRoot 'bootstrap_studio.py')
if ($LASTEXITCODE -ne 0) { throw 'Workbench initialization failed.' }
& $venvPython -c "import requests,PIL,filelock,markdown_it,imageio_ffmpeg,av,edge_tts,jwt; print('Web/media imports ready')"
if ($LASTEXITCODE -ne 0) { throw 'Runtime import check failed. Keep logs and rerun Install.cmd.' }
if (-not $SkipRenderers) { & (Join-Path $PSScriptRoot 'Install-Renderers.ps1') }
Write-Host 'Ready. Run Start.cmd. Codex can write storyboards; CPU renderers need no AI model.'
if ($SkipRenderers) { Write-Host 'Renderers skipped. Run scripts/Install-Renderers.ps1 before previewing.' }
Write-Host 'Offline basic narration uses installed Windows voices; optional online/local voices use your own configuration.'
Write-Host 'No AI model weights, voice samples, or API credentials have been installed.'

param([switch]$IncludeLocalCaption, [string]$PythonPath, [string]$NodePath, [string]$NpmCliPath)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'
if ($PythonPath) { $python = $PythonPath }
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
if ($python -like '*WindowsApps*') { throw 'Run Install-Studio.ps1 first, or supply -PythonPath with a real Python executable.' }
$node = Join-Path $studioRoot 'tools/node/node.exe'
if ($NodePath) { $node = $NodePath }
if (-not (Test-Path -LiteralPath $node)) { $node = (Get-Command node -ErrorAction Stop).Source }
$npm = Join-Path (Split-Path $node -Parent) 'node_modules/npm/bin/npm-cli.js'
if ($NpmCliPath) { $npm = $NpmCliPath }
if (-not (Test-Path -LiteralPath $npm)) { throw 'Install Node.js with npm, or run Install-Renderers.ps1 first.' }
$manifest = Get-Content -LiteralPath (Join-Path $studioRoot 'workflows/video-tools.json') -Raw | ConvertFrom-Json
& $python (Join-Path $PSScriptRoot 'install_video_tools.py')
if ($LASTEXITCODE -ne 0) { throw 'Video skill installation failed; existing files were preserved.' }
$runtime = Join-Path $studioRoot 'tools/video-runtime'
$versions = $manifest.runtime
& $node $npm install --prefix $runtime --save-exact --ignore-scripts --no-audit --no-fund "hyperframes@$($versions.hyperframes)" "@remotion/bundler@$($versions.remotion)" "@remotion/renderer@$($versions.remotion)" "remotion@$($versions.remotion)" "react@$($versions.react)" "react-dom@$($versions.react)" "ffprobe-static@$($versions.'ffprobe-static')" "gsap@$($versions.gsap)"
if ($LASTEXITCODE -ne 0) { throw 'Video renderer dependencies failed to install.' }
$ffmpeg = Join-Path $studioRoot 'tools/ffmpeg.exe'
if (-not (Test-Path -LiteralPath $ffmpeg)) {
    $ffmpegSource = & $python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'
    if ($LASTEXITCODE -ne 0) { throw 'Install the workbench Python requirements first.' }
    Copy-Item -LiteralPath $ffmpegSource.Trim() -Destination $ffmpeg
}
if ($IncludeLocalCaption) {
    $caption = Join-Path $studioRoot 'tools/video-skills/agent-caption'
    Push-Location $caption
    try { & $python setup.py; if ($LASTEXITCODE -ne 0) { throw 'Local caption setup failed.' } }
    finally { Pop-Location }
}
Write-Host 'Video Skills and CPU renderers installed. Online providers use workbench settings. Model weights are only needed for selected local engines.'

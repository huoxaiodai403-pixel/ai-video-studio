[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
. (Join-Path $PSScriptRoot 'Studio-Setup.ps1')
$studioRoot = Split-Path $PSScriptRoot -Parent
$studioPython = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Run Install-Studio.ps1 first.' }
& $studioPython (Join-Path $PSScriptRoot 'simon_source.py')
if ($LASTEXITCODE -ne 0) { throw 'The bundled Simon runtime is missing or modified. Restore it from the matching release; existing files were preserved.' }
$nodeRoot = Join-Path $studioRoot 'tools/node'
$nodeExe = Join-Path $nodeRoot 'node.exe'
$cacheRoot = Join-Path $studioRoot 'cache/setup'
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $nodeExe) -or -not (Test-Path -LiteralPath (Join-Path $nodeRoot 'node_modules/npm/bin/npm-cli.js'))) {
    $runtime = Get-Content -LiteralPath (Join-Path $studioRoot 'runtime-dependencies.json') -Raw | ConvertFrom-Json
    $nodeVersion = $runtime.renderers.node.version
    $archiveName = "node-v$nodeVersion-win-x64.zip"
    $archive = Join-Path $cacheRoot $archiveName
    Write-Host "Installing pinned Node.js $nodeVersion..."
    Get-StudioArchive $runtime.renderers.node.url $runtime.renderers.node.sha256 $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $cacheRoot -Force
    Save-StudioRuntime $nodeRoot $studioRoot
    New-Item -ItemType Directory -Path $nodeRoot -Force | Out-Null
    foreach ($file in (Get-ChildItem -LiteralPath (Join-Path $cacheRoot "node-v$nodeVersion-win-x64"))) {
        Copy-Item -LiteralPath $file.FullName -Destination $nodeRoot -Recurse
    }
}
$env:PATH = $nodeRoot + ';' + (Join-Path $studioRoot 'tools') + ';' + $env:PATH
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $studioRoot 'cache/ms-playwright'
$npm = Join-Path $nodeRoot 'node_modules/npm/bin/npm-cli.js'
$simonRoot = Join-Path $studioRoot 'apps/simon-skills'
# The tested fork, Windows patch, font and public stickers ship in the ZIP.
# End users do not need Git, repository access, or a second source download.
$whiteboard = Join-Path $simonRoot 'skills/whiteboard-video'
Push-Location $whiteboard
try {
    Write-Host 'Installing whiteboard renderer and Chromium...'
    & $nodeExe $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Whiteboard dependencies failed to install.' }
    & $nodeExe (Join-Path $whiteboard 'node_modules/playwright/cli.js') install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium download failed; rerun this script to retry.' }
    & $nodeExe (Join-Path $PSScriptRoot 'check_renderers.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Chromium could not launch; the renderer is not ready.' }
} finally { Pop-Location }
$renderer = Join-Path $studioRoot 'apps/investigation-renderer'
Push-Location $renderer
try {
    Write-Host 'Installing investigation renderer...'
    & $nodeExe $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Investigation renderer dependencies failed to install.' }
} finally { Pop-Location }
Write-Host 'CPU renderers ready. Use Windows voices, configured online/local speech, or prepared audio for narrated films.'

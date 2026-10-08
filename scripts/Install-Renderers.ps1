[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
$studioRoot = Split-Path $PSScriptRoot -Parent
$studioPython = Join-Path $studioRoot 'tools/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Run Install-Studio.ps1 first.' }
& $studioPython (Join-Path $PSScriptRoot 'simon_source.py')
if ($LASTEXITCODE -ne 0) { throw 'The bundled Simon runtime is missing or modified. Restore it from the matching release; existing files were preserved.' }
$nodeRoot = Join-Path $studioRoot 'tools/node'
$nodeExe = Join-Path $nodeRoot 'node.exe'
$cacheRoot = Join-Path $studioRoot 'cache/setup'
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $nodeExe) -or -not (Test-Path -LiteralPath (Join-Path $nodeRoot 'npm.cmd'))) {
    # Pinned Node.js LTS archive, verified against the publisher's SHA-256 manifest.
    $nodeVersion = '24.19.0'
    $archiveName = "node-v$nodeVersion-win-x64.zip"
    $downloadBase = "https://nodejs.org/dist/v$nodeVersion"
    $manifest = (Invoke-WebRequest -UseBasicParsing -Uri "$downloadBase/SHASUMS256.txt").Content
    $hashLine = ($manifest -split "`n" | Where-Object { $_.Trim().EndsWith(" $archiveName") } | Select-Object -First 1)
    if (-not $hashLine) { throw 'Node.js checksum was not found.' }
    $archive = Join-Path $cacheRoot $archiveName
    Invoke-WebRequest -UseBasicParsing -Uri "$downloadBase/$archiveName" -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne ($hashLine -split '\s+')[0]) { throw 'Node.js download checksum did not match.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $cacheRoot -Force
    New-Item -ItemType Directory -Path $nodeRoot -Force | Out-Null
    foreach ($file in (Get-ChildItem -LiteralPath (Join-Path $cacheRoot "node-v$nodeVersion-win-x64"))) {
        if (-not (Test-Path -LiteralPath (Join-Path $nodeRoot $file.Name))) { Copy-Item -LiteralPath $file.FullName -Destination $nodeRoot -Recurse }
    }
}
$env:PATH = $nodeRoot + ';' + (Join-Path $studioRoot 'tools') + ';' + $env:PATH
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $studioRoot 'cache/ms-playwright'
$npm = Join-Path $nodeRoot 'npm.cmd'
$simonRoot = Join-Path $studioRoot 'apps/simon-skills'
# The tested fork, Windows patch, font and public stickers ship in the ZIP.
# End users do not need Git, repository access, or a second source download.
$whiteboard = Join-Path $simonRoot 'skills/whiteboard-video'
Push-Location $whiteboard
try {
    & $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Whiteboard dependencies failed to install.' }
    & $nodeExe (Join-Path $whiteboard 'node_modules/playwright/cli.js') install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium download failed; rerun this script to retry.' }
    & $nodeExe (Join-Path $PSScriptRoot 'check_renderers.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Chromium could not launch; the renderer is not ready.' }
} finally { Pop-Location }
$renderer = Join-Path $studioRoot 'apps/investigation-renderer'
Push-Location $renderer
try {
    & $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Investigation renderer dependencies failed to install.' }
} finally { Pop-Location }
Write-Host 'CPU renderers ready. Speech models or prepared audio/alignment are still required for full video production.'

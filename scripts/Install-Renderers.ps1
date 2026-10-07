[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path $PSScriptRoot -Parent
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
$simonRevision = '3ad0a25127c17da48a0e869c9efbf4136c40848b'
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows, then run this script again.' }
if (-not (Test-Path -LiteralPath $simonRoot)) {
    & git.exe clone --no-checkout https://github.com/trustfuture/simon-skills.git $simonRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the Simon source.' }
    & git.exe -C $simonRoot checkout --detach $simonRevision
    if ($LASTEXITCODE -ne 0) { throw 'Could not check out the tested Simon revision.' }
}
$actualRevision = & git.exe -C $simonRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $simonRevision) { throw 'The existing Simon checkout has a different revision. Existing files were preserved.' }
$patch = Join-Path $studioRoot 'workflows/simon-windows.patch'
$patchProbe = Start-Process -FilePath (Get-Command git.exe).Source -ArgumentList @('-C', ('"'+$simonRoot+'"'), 'apply', '--reverse', '--check', ('"'+$patch+'"')) -WindowStyle Hidden -PassThru -Wait -RedirectStandardError (Join-Path $cacheRoot 'simon-patch-check.log')
if ($patchProbe.ExitCode -ne 0) {
    & git.exe -C $simonRoot apply --check $patch
    if ($LASTEXITCODE -ne 0) { throw 'The Windows patch conflicts with local changes; existing files were preserved.' }
    & git.exe -C $simonRoot apply $patch
    if ($LASTEXITCODE -ne 0) { throw 'Could not apply the Windows compatibility patch.' }
}
$whiteboard = Join-Path $simonRoot 'skills/whiteboard-video'
Push-Location $whiteboard
try {
    & $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Whiteboard dependencies failed to install.' }
    & $nodeExe (Join-Path $whiteboard 'node_modules/playwright/cli.js') install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium download failed; rerun this script to retry.' }
} finally { Pop-Location }
$renderer = Join-Path $studioRoot 'apps/investigation-renderer'
Push-Location $renderer
try {
    & $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Investigation renderer dependencies failed to install.' }
} finally { Pop-Location }
Write-Host 'CPU renderers ready. Speech models or prepared audio/alignment are still required for full video production.'

# Shared, process-local installation helpers. No administrator or system PATH changes.
function Test-StudioPython([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        $info = & $Executable -I -c 'import sys,venv,ensurepip; print(sys.version_info.major, sys.version_info.minor, sys.maxsize.bit_length())' 2>$null
        return ($LASTEXITCODE -eq 0 -and $info -match '^3 (11|12|13|14) 63$')
    } catch { return $false }
}

function Get-StudioArchive([string]$Url, [string]$Sha256, [string]$Destination) {
    if ($Url -notmatch '^https://' -or $Sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid pinned runtime download.' }
    if ((Test-Path -LiteralPath $Destination) -and (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Sha256) { return }
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile ($Destination + '.download') -TimeoutSec 180
            if ((Get-FileHash -LiteralPath ($Destination + '.download') -Algorithm SHA256).Hash -ne $Sha256) { throw 'Download checksum did not match; the archive was not executed.' }
            Move-Item -LiteralPath ($Destination + '.download') -Destination $Destination -Force
            return
        } catch {
            if ($attempt -eq 3) { throw "Runtime download failed: $Url. Check network/proxy and rerun Install.cmd. $($_.Exception.Message)" }
            Start-Sleep -Seconds 2
        }
    }
}

function Save-StudioRuntime([string]$Directory, [string]$Root) {
    # A copied/broken environment is recoverable; never delete user files to repair it.
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $resolved = [IO.Path]::GetFullPath($Directory)
    if (-not $resolved.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime backup is outside the workbench.' }
    if (Test-Path -LiteralPath $resolved) {
        if ((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Runtime directory must not be a link.' }
        $backup = $resolved + '.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
        Move-Item -LiteralPath $resolved -Destination $backup
        Write-Host "Previous runtime preserved: $backup"
    }
}

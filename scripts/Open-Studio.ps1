param([ValidateRange(1024,65535)][int]$Port=8189, [switch]$NoBrowser)
$ErrorActionPreference='Stop'
try {
    & (Join-Path $PSScriptRoot 'Start-Studio.ps1') -Port $Port
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/home" }
} catch {
    if ($NoBrowser) { Write-Error $_; exit 1 }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'AI Video Workbench') | Out-Null
    exit 1
}

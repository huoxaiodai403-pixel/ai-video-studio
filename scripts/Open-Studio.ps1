$ErrorActionPreference='Stop'
try {
    & (Join-Path $PSScriptRoot 'Start-Studio.ps1')
    $ready=$false
    for($attempt=0;$attempt -lt 30;$attempt++) {
        $client=New-Object System.Net.Sockets.TcpClient
        try { $client.Connect('127.0.0.1',8189); $ready=$true; break }
        catch { Start-Sleep -Seconds 1 }
        finally { $client.Dispose() }
    }
    if(-not $ready){throw ('The workbench did not start. Check '+(Join-Path (Split-Path $PSScriptRoot -Parent) 'logs/studio.err.log'))}
    Start-Process 'http://127.0.0.1:8189/'
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'AI Video Workbench') | Out-Null
    exit 1
}

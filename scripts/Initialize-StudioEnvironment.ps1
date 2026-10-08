# Normalize inherited Path/path/PATH aliases before PowerShell starts a child.
# Only the current process is changed; machine and user PATH stay untouched.
$studioEnvironment = [Environment]::GetEnvironmentVariables('Process')
$studioPathKeys = @($studioEnvironment.Keys | Where-Object { $_ -ieq 'Path' })
if ($studioPathKeys.Count -gt 1) {
    $studioPathParts = foreach ($studioPathKey in $studioPathKeys) {
        ([string]$studioEnvironment[$studioPathKey]) -split ';' | Where-Object { $_ }
    }
    $studioProcessPath = ($studioPathParts | Select-Object -Unique) -join ';'
    foreach ($studioPathKey in $studioPathKeys) {
        [Environment]::SetEnvironmentVariable($studioPathKey, $null, 'Process')
    }
    [Environment]::SetEnvironmentVariable('Path', $studioProcessPath, 'Process')
}

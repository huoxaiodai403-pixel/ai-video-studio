param([string]$Project='demo',[ValidateSet('all','tts','align','images','render')][string]$Stage='all',[switch]$Force)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if (-not [IO.Path]::IsPathRooted($Project)) { $Project=Join-Path $root "projects\$Project" }
$env:PYTHONUTF8='1'
$arguments=@((Join-Path $PSScriptRoot 'pipeline.py'),$Project,'--stage',$Stage)
if ($Force) { $arguments+='--force' }
& (Join-Path $root 'tools\.venv\Scripts\python.exe') @arguments
if ($LASTEXITCODE -ne 0) { throw "Video pipeline failed; inspect $Project logs." }

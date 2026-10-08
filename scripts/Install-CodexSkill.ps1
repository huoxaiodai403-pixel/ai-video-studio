param([string]$SkillSource = '', [string]$SkillsDirectory = '')
$ErrorActionPreference = 'Stop'
if (-not $SkillSource) {
    $candidates = @((Join-Path $PSScriptRoot '../skills/ai-video-studio'), (Join-Path $PSScriptRoot 'ai-video-studio'))
    $SkillSource = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'SKILL.md') } | Select-Object -First 1
}
if (-not $SkillSource -or -not (Test-Path -LiteralPath (Join-Path $SkillSource 'SKILL.md'))) { throw 'Cannot find ai-video-studio/SKILL.md. Keep the extracted package together.' }
if (-not $SkillsDirectory) {
    $codexSkillBase = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $SkillsDirectory = Join-Path $codexSkillBase 'skills'
}
$sourcePath = [IO.Path]::GetFullPath($SkillSource)
$skillsPath = [IO.Path]::GetFullPath($SkillsDirectory)
$targetPath = Join-Path $skillsPath 'ai-video-studio'
if ($sourcePath.TrimEnd('\') -eq $targetPath.TrimEnd('\')) { throw 'Source and destination are the same directory.' }
if ((Get-Item -LiteralPath $sourcePath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The source must be a real directory.' }
New-Item -ItemType Directory -Force -Path $skillsPath | Out-Null
if (Test-Path -LiteralPath $targetPath) {
    if ((Get-Item -LiteralPath $targetPath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to overwrite a linked skill directory.' }
    $backupPath = Join-Path (Split-Path $skillsPath -Parent) ('skill-backups/ai-video-studio-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Force -Path (Split-Path $backupPath -Parent) | Out-Null
    Copy-Item -LiteralPath $targetPath -Destination $backupPath -Recurse
    Write-Host "Previous skill backed up: $backupPath"
}
New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
Get-ChildItem -LiteralPath $sourcePath -Force | Copy-Item -Destination $targetPath -Recurse -Force
Write-Host "Installed skill: $targetPath"
Write-Host 'Start a new Codex conversation and use $ai-video-studio. Install the workbench separately; add media engines only when the requested task needs them.'

@echo off
setlocal
if not exist "%~dp0scripts\Install-Studio.ps1" (
  echo The installer is missing. Check antivirus quarantine and verify the source package before retrying.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Install-Studio.ps1" -InstallPython
if errorlevel 1 (echo Installation failed. See the message above. & pause & exit /b 1)
echo Installation complete. Open Start.cmd to launch the workbench.
pause

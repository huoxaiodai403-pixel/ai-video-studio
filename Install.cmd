@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Install-Studio.ps1" -InstallPython
if errorlevel 1 (echo Installation failed. See the message above. & pause & exit /b 1)
echo Installation complete. Open Start.cmd to launch the workbench.
pause

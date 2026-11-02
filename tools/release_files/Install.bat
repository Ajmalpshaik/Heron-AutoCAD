@echo off
rem Double-click to install Heron AI for AutoCAD. Add the word uninstall to remove it.
if /I "%~1"=="uninstall" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" -Uninstall
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
)
pause

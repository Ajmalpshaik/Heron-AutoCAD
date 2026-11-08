@echo off
rem Double-click to remove Heron AI for AutoCAD. It shows what it removes and asks first.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" -Uninstall
pause

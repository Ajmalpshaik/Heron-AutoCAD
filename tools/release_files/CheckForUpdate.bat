@echo off
rem Double-click to see whether a newer Heron is out. It never installs anything by itself.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" -CheckUpdate
pause

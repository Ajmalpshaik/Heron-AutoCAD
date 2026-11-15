@echo off
rem Double-click to go back to the Heron version this one replaced. It shows both and asks first.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" -Rollback
pause

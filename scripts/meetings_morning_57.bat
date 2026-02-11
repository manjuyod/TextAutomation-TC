@echo off
setlocal
cd /d "%~dp0.."
uv run text-automation meetings morning --franchise-id 57
endlocal


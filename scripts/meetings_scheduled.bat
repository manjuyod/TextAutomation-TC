@echo off
setlocal
cd /d "%~dp0.."
uv run text-automation meetings scheduled
endlocal


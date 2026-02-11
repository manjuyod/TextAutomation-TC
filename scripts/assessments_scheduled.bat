@echo off
setlocal
REM Change to repo root (this script is in scripts/)
cd /d "%~dp0.."
uv run text-automation assessments scheduled
endlocal


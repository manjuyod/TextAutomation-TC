@echo off
setlocal
cd /d "%~dp0.."
uv run text-automation assessments morning --franchise-id 1
endlocal


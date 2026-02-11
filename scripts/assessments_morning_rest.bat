@echo off
setlocal
cd /d "%~dp0.."
REM All configured franchises except 57
uv run text-automation assessments morning --franchise-id 1,2,3,6,11,15,16,19,20,24,60,87,57,103
endlocal


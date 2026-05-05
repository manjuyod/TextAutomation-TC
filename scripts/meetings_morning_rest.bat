@echo off
setlocal
cd /d "%~dp0.."
REM All configured franchises except 57
uv run text-automation meetings morning --franchise-id 1,6,11,15,16,19,20,24,49,60,87,103,110
endlocal

@echo off
setlocal enabledelayedexpansion
REM Change to repo root (this script is in scripts/)
cd /d "%~dp0.."

set EXTRA_ARGS=%*

uv run text-automation inquiry-followup run %EXTRA_ARGS%
endlocal

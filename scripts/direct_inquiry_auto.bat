@echo off
setlocal
cd /d "%~dp0.."

REM Forward any extra args (e.g., --dry-run) to the command
set EXTRA_ARGS=%*
echo [%DATE% %TIME%] Running Direct Inquiry (mode=auto) %EXTRA_ARGS%
uv run text-automation direct-inquiry process --mode auto --max 50 %EXTRA_ARGS%

endlocal


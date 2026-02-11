@echo off
setlocal
cd /d "%~dp0.."

REM Forward any extra args (e.g., --dry-run) to the command
set EXTRA_ARGS=%*
echo [%DATE% %TIME%] Running Student Intake (max=50) %EXTRA_ARGS%
uv run text-automation student-intake process --max 50 %EXTRA_ARGS%

endlocal


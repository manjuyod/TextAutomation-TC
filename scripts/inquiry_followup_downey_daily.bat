@echo off
setlocal enabledelayedexpansion
REM Change to repo root (this script is in scripts/)
cd /d "%~dp0.."

set /a BATCH_SIZE=40 + (%RANDOM% %% 3)
set /a SLEEP_SECONDS=20 + (%RANDOM% %% 26)

echo [inquiry_followup_downey_daily] batch_size=!BATCH_SIZE! sleep_seconds=!SLEEP_SECONDS!

uv run text-automation inquiry-followup run --franchise-id 87 --since 2024-01-01 --min-age-days 7 --batch-size !BATCH_SIZE! --max-batches 1 --sleep-seconds !SLEEP_SECONDS! %*
endlocal

@echo off
setlocal
cd /d "%~dp0.."

REM One-time Gravity Forms baseline for main-site direct inquiries.
REM This marks unread target-form entries as read without creating SQL inquiries
REM or sending Zapier/text automation. Pass --dry-run first to preview counts.
set EXTRA_ARGS=%*
echo [%DATE% %TIME%] Running Gravity Forms Direct Inquiry baseline %EXTRA_ARGS%
uv run text-automation wordpress gravity-forms baseline-direct-inquiry %EXTRA_ARGS%
set EXIT_CODE=%ERRORLEVEL%

endlocal & exit /b %EXIT_CODE%

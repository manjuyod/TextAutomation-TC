@echo off
setlocal
cd /d "%~dp0.."

REM Forward all extra args to Gravity Forms. Gmail only receives --dry-run,
REM since GF-specific args such as --form-id are not valid for Gmail.
set EXTRA_ARGS=%*
set GMAIL_EXTRA_ARGS=
for %%A in (%*) do (
  if /I "%%~A"=="--dry-run" set GMAIL_EXTRA_ARGS=--dry-run
)
echo [%DATE% %TIME%] Running Gravity Forms Direct Inquiry %EXTRA_ARGS%
uv run text-automation wordpress gravity-forms process-direct-inquiry --limit 50 %EXTRA_ARGS%
if errorlevel 1 exit /b %errorlevel%

REM Keep the Gmail path for location-specific notification emails. Main-site
REM no-location emails are marked read without SQL/text by the processor.
echo [%DATE% %TIME%] Running location-specific Gmail Direct Inquiry (mode=auto) %GMAIL_EXTRA_ARGS%
uv run text-automation direct-inquiry process --mode auto --max 50 %GMAIL_EXTRA_ARGS%

endlocal


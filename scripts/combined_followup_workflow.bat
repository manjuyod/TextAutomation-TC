@echo off
setlocal enabledelayedexpansion
REM Change to repo root (this script is in scripts/)
cd /d "%~dp0.."

REM Pass all extra args to Gravity Forms and scheduled workflows. Gmail only
REM receives --dry-run, since GF-specific args such as --form-id are invalid.
set EXTRA_ARGS=%*
set GMAIL_EXTRA_ARGS=
for %%A in (%*) do (
  if /I "%%~A"=="--dry-run" set GMAIL_EXTRA_ARGS=--dry-run
)

echo [%%DATE%% %%TIME%%] Starting combined scheduled workflow

echo [%DATE% %TIME%] Running Gravity Forms Direct Inquiry %EXTRA_ARGS%
uv run text-automation wordpress gravity-forms process-direct-inquiry --limit 50 %EXTRA_ARGS%
if errorlevel 1 (
  echo [%%DATE%% %%TIME%%] Gravity Forms Direct Inquiry failed with errorlevel !errorlevel!
  exit /b !errorlevel!
)

echo [%DATE% %TIME%] Running location-specific Gmail Direct Inquiry (mode=auto) %GMAIL_EXTRA_ARGS%
uv run text-automation direct-inquiry process --mode auto --max 50 %GMAIL_EXTRA_ARGS%
if errorlevel 1 (
  echo [%%DATE%% %%TIME%%] Gmail Direct Inquiry failed with errorlevel !errorlevel!
  exit /b !errorlevel!
)

echo [%%DATE%% %%TIME%%] Running assessments scheduled %EXTRA_ARGS%
uv run text-automation assessments scheduled %EXTRA_ARGS%
if errorlevel 1 (
  echo [%%DATE%% %%TIME%%] Assessments scheduled failed with errorlevel !errorlevel!
  exit /b !errorlevel!
)

echo [%%DATE%% %%TIME%%] Running meetings scheduled %EXTRA_ARGS%
uv run text-automation meetings scheduled %EXTRA_ARGS%
if errorlevel 1 (
  echo [%%DATE%% %%TIME%%] Meetings scheduled failed with errorlevel !errorlevel!
  exit /b !errorlevel!
)

echo [%DATE% %TIME%] Running Student Intake (max=50) %EXTRA_ARGS%
uv run text-automation student-intake process --max 50 %EXTRA_ARGS%
if errorlevel 1 (
  echo [%%DATE%% %%TIME%%] Student Intake failed with errorlevel !errorlevel!
  exit /b !errorlevel!
)

echo [%%DATE%% %%TIME%%] Combined scheduled workflow completed
endlocal

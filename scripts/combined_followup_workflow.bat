@echo off
setlocal enabledelayedexpansion
REM Change to repo root (this script is in scripts/)
cd /d "%~dp0.."

REM Pass any extra args (e.g., --dry-run) through to both commands
set EXTRA_ARGS=%*

echo [%%DATE%% %%TIME%%] Starting combined scheduled workflow

echo [%DATE% %TIME%] Running Direct Inquiry (mode=auto) %EXTRA_ARGS%
uv run text-automation direct-inquiry process --mode auto --max 50 %EXTRA_ARGS%
if errorlevel 1 (
  echo [%%DATE%% %%TIME%%] Direct to Inquiry failed with errorlevel !errorlevel!
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

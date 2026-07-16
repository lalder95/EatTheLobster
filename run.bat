@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%.venv\Scripts\python.exe" -m app.main
) else (
    py -3 -m app.main
)

if %ERRORLEVEL% NEQ 0 (
    echo Application exited with an error.
    pause
)

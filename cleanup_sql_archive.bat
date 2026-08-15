@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%.venv\Scripts\python.exe" cleanup_sql_archive.py %*
) else (
    py -3 cleanup_sql_archive.py %*
)

if %ERRORLEVEL% NEQ 0 (
    echo SQL archive cleanup exited with an error.
    pause
)
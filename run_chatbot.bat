@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%.venv\Scripts\python.exe" -m chatbot_app.main
) else (
    py -3 -m chatbot_app.main
)

if %ERRORLEVEL% NEQ 0 (
    echo Chatbot application exited with an error.
    pause
)
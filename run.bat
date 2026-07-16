@echo off
cd /d "%~dp0"
python -m app.main
if %ERRORLEVEL% NEQ 0 (
    echo Application exited with an error.
    pause
)

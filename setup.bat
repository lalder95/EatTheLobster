@echo off
echo Installing ETL Importer dependencies...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Installation failed. Make sure Python 3.11+ and pip are available.
    pause
    exit /b 1
)
echo.
echo NOTE: SQL Server connections require "ODBC Driver 18 for SQL Server".
echo       If you plan to connect to MS SQL Server, download and install it from:
echo       https://aka.ms/downloadmsodbcsql
echo.
echo Done. Run "run.bat" to start the application.
pause

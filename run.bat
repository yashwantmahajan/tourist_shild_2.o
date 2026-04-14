@echo off
set PYTHONIOENCODING=utf-8
echo ========================================
echo   Tourist Shield Application Launcher (Production)
echo ========================================
echo.

REM Navigate to project directory
cd /d "%~dp0"

REM Check if database exists
if not exist "instance\tourist_shield.db" (
    echo Database not found. Initializing...
    python init_db.py
    echo.
)

REM Start the application
echo Starting Tourist Shield Production Server...
echo.
echo Once started, open your browser and go to:
echo http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo.
python -m waitress --host=127.0.0.1 --port=5000 app:app

REM Keep the window open after the application exits
pause

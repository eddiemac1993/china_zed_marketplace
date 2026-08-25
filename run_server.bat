@echo off
title ChinaZed Marketplace Server
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found in .venv
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Starting ChinaZed Marketplace server...
echo Open http://127.0.0.1:8000/ in your browser once it starts.
echo Press CTRL+C to stop the server.
echo.

python manage.py runserver 127.0.0.1:8000

pause

@echo off
chcp 65001 >nul
title PowerMill AI - состояние базы знаний
cd /d "%~dp0\.."

if not exist "venv\Scripts\python.exe" (
    echo [!] Нет venv - запусти setup.bat
    pause
    exit /b 1
)
call venv\Scripts\activate
python -m scripts.base_status
echo.
pause

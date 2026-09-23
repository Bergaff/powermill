
@echo off
chcp 65001 >nul
title PowerMill AI - тесты
cd /d "%~dp0\.."

if not exist "venv\Scripts\python.exe" (
    echo [!] Нет venv - запусти setup.bat
    pause
    exit /b 1
)
call venv\Scripts\activate

echo =========================================================
echo   ТЕСТЫ (синтетическая справка, без ИИ и без Ollama)
echo =========================================================
echo.
python -m pytest tests -q
echo.
pause

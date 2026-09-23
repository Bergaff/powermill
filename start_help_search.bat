@echo off
chcp 65001 >nul
title PowerMill AI - поиск по справке (без ИИ)
cd /d "%~dp0"

echo =========================================================
echo   ПОИСК ПО СПРАВКЕ PowerMill  —  без ИИ, мгновенно
echo   Работает на ключевых словах, эмбеддинги не нужны.
echo   Если ответа нет — сначала разбери справку:
echo       start_parse_help.bat
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение не найдено.
    echo     Сначала запусти setup.bat
    pause
    exit /b 1
)

call venv\Scripts\activate

if not "%~1"=="" (
    python -m src.help_search %*
) else (
    python -m src.help_search
)

echo.
pause

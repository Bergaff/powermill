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

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Виртуального окружения нет - работаю системным Python.
    echo     Если чего-то не хватает - запусти setup_light.bat (1 минута)
    echo.
)

if not "%~1"=="" (
    python -m src.help_search %*
) else (
    python -m src.help_search
)

echo.
pause

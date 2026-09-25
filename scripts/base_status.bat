@echo off
chcp 65001 >nul
title PowerMill AI - состояние базы знаний
cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Виртуального окружения нет - работаю системным Python.
    echo     Если чего-то не хватает - запусти setup_light.bat (1 минута)
    echo.
)
python -m scripts.base_status
echo.
pause

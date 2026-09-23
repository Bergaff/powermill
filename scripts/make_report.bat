@echo off
chcp 65001 >nul
title PowerMill AI - отчёт для отправки в чат
cd /d "%~dp0\.."

echo =========================================================
echo   ГОТОВЛЮ ОТЧЁТ ОБ УСТАНОВКЕ И БАЗЕ ЗНАНИЙ
echo   Один файл, который можно целиком прислать в чат.
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Виртуального окружения нет - работаю системным Python.
    echo     Если чего-то не хватает - запусти setup_light.bat (1 минута)
    echo.
)

python -m scripts.make_report
if errorlevel 1 (
    echo [!] Не удалось подготовить отчёт
    pause
    exit /b 1
)

echo.
echo Открываю отчёт в блокноте - скопируй его целиком в чат.
start "" notepad "output\OTCHET_DLYA_CHATA.txt"
pause

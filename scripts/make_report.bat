@echo off
chcp 65001 >nul
title PowerMill AI - отчёт для отправки в чат
cd /d "%~dp0\.."

echo =========================================================
echo   ГОТОВЛЮ ОТЧЁТ ОБ УСТАНОВКЕ И БАЗЕ ЗНАНИЙ
echo   Один файл, который можно целиком прислать в чат.
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [!] Нет venv - запусти setup.bat
    pause
    exit /b 1
)
call venv\Scripts\activate

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

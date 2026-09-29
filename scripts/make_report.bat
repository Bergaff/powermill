@echo off
chcp 65001 >nul
title PowerMill AI - отчёт для отправки в чат
cd /d "%~dp0.."

echo =========================================================
echo   ГОТОВЛЮ ОТЧЁТ ОБ УСТАНОВКЕ И БАЗЕ ЗНАНИЙ
echo   Один файл, который можно целиком прислать в чат.
echo =========================================================
echo.

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

"%PY%" -m scripts.make_report
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed

echo.
echo Открываю отчёт в блокноте - скопируй его целиком в чат.
start "" notepad "output\OTCHET_DLYA_CHATA.txt"
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo [!] Не удалось подготовить отчёт (код %RC%).
echo     Попробуй запустить пункт 18 меню (быстрая установка).
echo.
pause
exit /b 1

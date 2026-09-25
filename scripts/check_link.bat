@echo off
chcp 65001 >nul
title PowerMill AI - проверка связи с PowerMill
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.check_link
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto nolink
echo Связь есть. Отчёт: output\pm_link_report.txt (пункт 29 меню).
pause >nul
exit /b 0

:nolink
echo [!] Связи с PowerMill нет — смотри шаги выше.
echo     Что проверить: PowerMill запущен с проектом; пункт 27 (мост pywin32);
echo     окно PowerMill не занято диалогом.
echo     Отчёт: output\pm_link_report.txt.
echo.
pause
exit /b 1

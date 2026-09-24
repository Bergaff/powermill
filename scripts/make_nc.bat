@echo off
chcp 65001 >nul
title PowerMill AI - NC-программа из траекторий
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.make_nc
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт — пункт 29 меню (pm_nc_report.txt).
pause >nul
exit /b 0

:failed
echo [!] NC не вывелась (код %RC%).
echo     Что делать: проверь, что PowerMill запущен, в проекте есть посчитанная
echo     траектория (пункт 31) и указан постпроцессор станка.
echo     Отчёт — пункт 29 меню.
echo.
pause
exit /b 1

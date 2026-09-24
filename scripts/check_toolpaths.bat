@echo off
chcp 65001 >nul
title PowerMill AI - проверки траекторий (зарезы, столкновения)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.check_toolpaths
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт — пункт 29 меню (pm_check_report.txt).
pause >nul
exit /b 0

:failed
echo [!] Проверки не отработали (код %RC%).
echo     Что делать: проверь, что PowerMill запущен с проектом и в нём есть
echo     посчитанная траектория (пункт 31); отчёт — пункт 29.
echo.
pause
exit /b 1

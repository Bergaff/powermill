@echo off
chcp 65001 >nul
title PowerMill AI - панель на ленте PowerMill
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.make_ribbon
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт — пункт 29 меню (pm_ribbon_report.txt).
pause >nul
exit /b 0

:failed
echo [!] Вкладку добавить не получилось (код %RC%).
echo     Что делать: в PowerMill открой File - Options - Customise the Ribbon,
echo     закрой окно кнопкой OK и запусти пункт 34 снова; либо добавь кнопку
echo     руками — инструкция в отчёте (пункт 29) и в README.
echo.
pause
exit /b 1

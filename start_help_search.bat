@echo off
chcp 65001 >nul
title PowerMill AI - поиск по справке
setlocal
cd /d "%~dp0"

echo =========================================================
echo   ПОИСК ПО СПРАВКЕ PowerMill - без ИИ, мгновенно
echo =========================================================
echo.

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo [!] Виртуального окружения нет - работаю системным Python.
echo.
:run

"%PY%" -m scripts.preflight search
if errorlevel 1 goto failed

echo.
"%PY%" -m src.help_search %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo.
echo [!] Не получилось. Если справка ещё не разобрана:
echo     запусти start_parse_help.bat (пункт 4 меню)
echo.
pause
exit /b 1

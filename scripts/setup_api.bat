@echo off
chcp 65001 >nul
title PowerMill AI - подключение ИИ по API
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.setup_api
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo [!] Настройка API завершилась с ошибкой.
echo     Подробности в логе: scripts\show_logs.bat
echo.
pause
exit /b 1

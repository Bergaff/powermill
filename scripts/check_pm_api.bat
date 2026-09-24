@echo off
chcp 65001 >nul
title PowerMill AI - проверка связи с PowerMill
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.check_pm_api
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo [!] Проверка завершилась с ошибкой. Логи: scripts\show_logs.bat
echo.
pause
exit /b 1

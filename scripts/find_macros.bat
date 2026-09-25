@echo off
chcp 65001 >nul
title PowerMill AI - поиск макросов на диске
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.find_macros
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo [!] Поиск макросов завершился с ошибкой.
echo     Логи: scripts\show_logs.bat
echo.
pause
exit /b 1

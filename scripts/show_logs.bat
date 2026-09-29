@echo off
chcp 65001 >nul
title PowerMill AI - логи последних запусков
setlocal
cd /d "%~dp0\.."

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

"%PY%" -m scripts.show_logs

echo.
if exist "output\logs" start "" explorer "output\logs"
echo.
pause
exit /b 0

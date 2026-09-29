@echo off
chcp 65001 >nul
title PowerMill AI - состояние базы знаний
cd /d "%~dp0\.."

set "VENV=.venv\Scripts"
if not exist "%VENV%\python.exe" set "VENV=venv\Scripts"
if exist "%VENV%\python.exe" set "PATH=%CD%\%VENV%;%PATH%"
if not exist "%VENV%\python.exe" echo [!] Виртуального окружения нет - работаю системным Python - поставь install.bat
python -m scripts.base_status
echo.
pause

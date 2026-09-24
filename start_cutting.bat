@echo off
chcp 65001 >nul
title PowerMill AI - режимы резания
setlocal
cd /d "%~dp0"

echo =========================================================
echo   РЕЖИМЫ РЕЗАНИЯ - расчёт по формулам, без ИИ
echo   S (об/мин), F (мм/мин), ap, ae, мощность, стратегия
echo =========================================================
echo.

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" goto run
echo [!] Виртуального окружения нет - работаю системным Python.
echo.
:run

"%PY%" -m src.cutting %*
echo.
if not defined PM_FROM_MENU pause
exit /b 0

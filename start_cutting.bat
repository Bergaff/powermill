@echo off
chcp 65001 >nul
title PowerMill AI - режимы резания (S, F, ap, ae)
cd /d "%~dp0"

echo =========================================================
echo   РЕЖИМЫ РЕЗАНИЯ  —  расчёт по формулам, без ИИ
echo   S (об/мин), F (мм/мин), ap, ae, мощность, стратегия
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение не найдено.
    echo     Сначала запусти setup.bat
    pause
    exit /b 1
)

call venv\Scripts\activate

if not "%~1"=="" (
    python -m src.cutting %*
) else (
    python -m src.cutting
)

echo.
pause

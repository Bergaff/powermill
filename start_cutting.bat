@echo off
chcp 65001 >nul
title PowerMill AI - режимы резания (S, F, ap, ae)
cd /d "%~dp0"

echo =========================================================
echo   РЕЖИМЫ РЕЗАНИЯ  —  расчёт по формулам, без ИИ
echo   S (об/мин), F (мм/мин), ap, ae, мощность, стратегия
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Виртуального окружения нет - работаю системным Python.
    echo     Если чего-то не хватает - запусти setup_light.bat (1 минута)
    echo.
)

if not "%~1"=="" (
    python -m src.cutting %*
) else (
    python -m src.cutting
)

echo.
pause

@echo off
chcp 65001 >nul
title PowerMill AI [TURBO - ночная индексация]
set APP_MODE=turbo
setlocal
cd /d "%~dp0"

echo =========================================================
echo   НОЧНАЯ ПОЛНАЯ ИНДЕКСАЦИЯ (режим TURBO)
echo   PDF, справка HTML, видео, векторная база
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" goto no_venv
call venv\Scripts\activate

echo [1/4] PDF-документация из data\pdf ...
python -m src.pdf_parser
echo.

echo [2/4] Оффлайн-справка PowerMill ...
python -m src.html_parser
python -m src.help_search --rebuild
echo.

echo [3/4] Видеоуроки из data\videos ...
python -m src.video_parser
echo.

echo [4/4] Векторная база ChromaDB ...
python -m src.vectorstore
echo.

python -m scripts.base_status
echo.
echo =========================================================
echo   НОЧНАЯ ИНДЕКСАЦИЯ ЗАВЕРШЕНА
echo   Логи: output\logs\
echo =========================================================
echo.
pause
exit /b 0

:no_venv
echo [!] Нет venv - запусти setup.bat
echo.
pause
exit /b 1

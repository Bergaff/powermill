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

set "VENV=.venv\Scripts"
if not exist "%VENV%\python.exe" set "VENV=venv\Scripts"
if not exist "%VENV%\python.exe" goto no_venv
set "PATH=%CD%\%VENV%;%PATH%"
echo   Python: %CD%\%VENV%\python.exe

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
if errorlevel 2 echo     (нет библиотек: пункт 43 меню с ключом --all)
if errorlevel 1 echo     (в базу попали не все куски - смотри output\vector_db_report.txt)
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
echo [!] Нет виртуального окружения (ни .venv, ни venv).
echo     Запусти install.bat - он создаст .venv и поставит библиотеки.
echo     Библиотеки те же, что и программе: пункт 43 меню.
echo.
pause
exit /b 1

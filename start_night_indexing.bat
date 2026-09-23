@echo off
chcp 65001 >nul
title PowerMill AI [TURBO - ночная индексация]
set APP_MODE=turbo
cd /d "%~dp0"

echo =========================================================
echo   НОЧНАЯ ПОЛНАЯ ИНДЕКСАЦИЯ (режим TURBO)
echo   PDF -> справка HTML -> видео -> векторная база
echo   Запускай на ночь: загрузка CPU полная.
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение не найдено - запусти setup.bat
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate

echo [1/4] PDF-документация из data\pdf ...
python -m src.pdf_parser
if errorlevel 1 echo       ^(пропускаю: нет PDF или ошибка - не страшно^)

echo.
echo [2/4] Оффлайн-справка PowerMill + индекс поиска ...
python -m src.html_parser
if errorlevel 1 echo       ^(справка не найдена - scripts\set_help_path.bat^)
python -m src.help_search --rebuild

echo.
echo [3/4] Видеоуроки из data\videos (транскрипция Whisper)...
python -m src.video_parser
if errorlevel 1 echo       ^(пропускаю: нет видео или ошибка^)

echo.
echo [4/4] Векторная база ChromaDB на диске E: ...
python -m src.vectorstore
if errorlevel 1 (
    echo [!] Не удалось собрать векторную базу
    echo     Проверь: scripts\install_torch.bat
    echo     Отчёт:  scripts\make_report.bat
)

echo.
python -m scripts.base_status
echo.
echo =========================================================
echo   НОЧНАЯ ИНДЕКСАЦИЯ ЗАВЕРШЕНА
echo   Утром: start_work_chat.bat
echo =========================================================
pause

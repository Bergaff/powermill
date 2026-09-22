@echo off
chcp 65001 >nul
title PowerMill AI [TURBO - ночная индексация]
set APP_MODE=turbo
echo =======================================================
echo   PowerMill AI - НОЧНОЙ ТУРБО-РЕЖИМ
echo   * Максимум ресурсов CPU
echo   * VRAM держится в памяти между шагами
echo =======================================================
cd /d "%~dp0"
call venv\Scripts\activate

echo [1/3] Чтение и извлечение текста из PDF (диск E)...
python -m src.pdf_parser
if errorlevel 1 echo    (пропущено или ошибка - продолжаем)

echo.
echo [2/3] Транскрипция видео (если есть в data\videos на E:)...
python -m src.video_parser
if errorlevel 1 echo    (нет видео или ошибка - продолжаем)

echo.
echo [3/3] Создание векторной базы ChromaDB (диск E)...
python -m src.vectorstore

echo.
echo =======================================================
echo   Готово! Запускай start_work_chat.bat
echo =======================================================
pause

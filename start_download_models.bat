@echo off
chcp 65001 >nul
title PowerMill AI - Скачивание моделей Ollama на диск E
cd /d "%~dp0"

:: Все модели Ollama летят в E:\ollama_models (задано setup.bat / set_heavy_paths.bat)
set "OLLAMA_MODELS=E:\ollama_models"

where ollama >nul 2>nul
if errorlevel 1 (
    echo [!] Ollama не найден! Скачай с https://ollama.com/download/windows
    pause
    exit /b 1
)

echo Модели будут скачаны в: %OLLAMA_MODELS%
echo (это НЕ диск C - значит, SSD не забьётся)
echo.

echo [1/2] qwen2.5:3b - модель для чата (~2 ГБ)...
ollama pull qwen2.5:3b

echo.
echo [2/2] qwen2.5-coder:3b - модель для PML-макросов (~2 ГБ)...
ollama pull qwen2.5-coder:3b

echo.
echo =========================================================
echo   Проверка:
ollama list
echo.
echo   Все модели на E:\ollama_models
echo   Запуск чата: start_work_chat.bat
echo =========================================================
pause

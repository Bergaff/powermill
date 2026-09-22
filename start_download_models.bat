@echo off
chcp 65001 >nul
title PowerMill AI - Download Ollama models to disk E
cd /d "%~dp0"

set "OLLAMA_MODELS=E:\ollama_models"

where ollama >nul 2>nul
if errorlevel 1 (
    echo [!] Ollama not found! Download: https://ollama.com/download/windows
    pause
    exit /b 1
)

if not exist "E:\ollama_models" mkdir "E:\ollama_models"
echo Models will be downloaded to: %OLLAMA_MODELS%
echo (this is NOT disk C - your SSD stays free)
echo.

echo [1/2] qwen2.5:3b - chat model (~2 GB)...
ollama pull qwen2.5:3b

echo.
echo [2/2] qwen2.5-coder:3b - PML macro model (~2 GB)...
ollama pull qwen2.5-coder:3b

echo.
echo =========================================================
echo   Check:
ollama list
echo.
echo   All models are in E:\ollama_models
echo   Start chat with: start_work_chat.bat
echo =========================================================
pause

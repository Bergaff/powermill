@echo off
chcp 65001 >nul
title PowerMill AI - Установка (всё на диск E)
echo =========================================================
echo   PowerMill AI - Установка ВСЕГО на диск E
echo   Код:     E:\powermill
echo   Модели:  E:\ollama_models
echo   Кэш HF:  E:\hf_cache
echo   Кэш pip: E:\pip_cache
echo =========================================================
cd /d "%~dp0"

:: --- 1. Проверка Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python не найден! Скачай с https://www.python.org/downloads/
    echo     При установке отметь "Add Python to PATH".
    pause
    exit /b 1
)

:: --- 2. Переменные окружения: всё тяжёлое на E: (текущая сессия) ---
echo.
echo [1/5] Перенос путей на диск E...
set "POWERMILL_DATA_ROOT=E:\powermill"
set "OLLAMA_MODELS=E:\ollama_models"
set "HF_HOME=E:\hf_cache"
set "PIP_CACHE_DIR=E:\pip_cache"
if not exist "E:\ollama_models" mkdir "E:\ollama_models"
if not exist "E:\hf_cache" mkdir "E:\hf_cache"
if not exist "E:\pip_cache" mkdir "E:\pip_cache"
if not exist "E:\powermill\data\pdf" mkdir "E:\powermill\data\pdf"
if not exist "E:\powermill\data\videos" mkdir "E:\powermill\data\videos"
if not exist "E:\powermill\data\macros" mkdir "E:\powermill\data\macros"
if not exist "E:\powermill\data\forums" mkdir "E:\powermill\data\forums"

:: --- 3. Сохранить переменные навсегда (после закрытия окна) ---
echo [2/5] Сохраняю переменные окружения (setx)...
setx POWERMILL_DATA_ROOT "E:\powermill" >nul
setx OLLAMA_MODELS "E:\ollama_models" >nul
setx HF_HOME "E:\hf_cache" >nul
setx PIP_CACHE_DIR "E:\pip_cache" >nul
echo       POWERMILL_DATA_ROOT = E:\powermill
echo       OLLAMA_MODELS       = E:\ollama_models
echo       HF_HOME             = E:\hf_cache
echo       PIP_CACHE_DIR       = E:\pip_cache

:: --- 4. venv (рядом с кодом = E:\powermill\venv) ---
echo.
echo [3/5] Создание виртуального окружения на E:...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
) else (
    echo       venv уже существует - пропускаем
)
call venv\Scripts\activate

:: --- 5. Зависимости (кэш pip тоже на E:) ---
echo.
echo [4/5] Установка зависимостей (torch ~2 ГБ, кэш на E:)...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: --- 6. Проверка Ollama и моделей ---
echo.
echo [5/5] Проверка Ollama...
where ollama >nul 2>nul
if errorlevel 1 (
    echo [!] Ollama не найден!
    echo     Скачай: https://ollama.com/download/windows
    echo     ПОСЛЕ установки снова запусти setup.bat,
    echo     чтобы модели качались в E:\ollama_models
) else (
    echo       Ollama найдена. Скачай модели командой:
    echo       ollama pull qwen2.5:3b
    echo       ollama pull qwen2.5-coder:3b
)

echo.
echo =========================================================
echo   УСТАНОВКА ЗАВЕРШЕНА
echo   1. Положи PDF в E:\powermill\data\pdf
echo   2. Положи видео (по желанию) в E:\powermill\data\videos
echo   3. Положи .mac макросы (по желанию) в E:\powermill\data\macros
echo   4. Скачай модели: start_download_models.bat
echo   5. Ночная индексация: start_night_indexing.bat
echo   6. Чат: start_work_chat.bat
echo =========================================================
pause

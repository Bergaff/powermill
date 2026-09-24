@echo off
chcp 65001 >nul
title PowerMill AI - установка (всё тяжёлое на диск E:)
cd /d "%~dp0"

echo =========================================================
echo   PowerMill AI - УСТАНОВКА
echo   Код:       E:\powermill-ai
echo   Модели:    E:\ollama_models
echo   HF cache:  E:\hf_cache
echo   Pip cache: E:\pip_cache
echo =========================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto no_python

echo [1/6] Создаю папки на диске E: ...
set "POWERMILL_DATA_ROOT=E:\powermill-ai"
set "OLLAMA_MODELS=E:\ollama_models"
set "HF_HOME=E:\hf_cache"
set "PIP_CACHE_DIR=E:\pip_cache"
if not exist "E:\ollama_models" mkdir "E:\ollama_models"
if not exist "E:\hf_cache" mkdir "E:\hf_cache"
if not exist "E:\pip_cache" mkdir "E:\pip_cache"
if not exist "E:\powermill-ai\data\pdf" mkdir "E:\powermill-ai\data\pdf"
if not exist "E:\powermill-ai\data\videos" mkdir "E:\powermill-ai\data\videos"
if not exist "E:\powermill-ai\data\macros" mkdir "E:\powermill-ai\data\macros"
if not exist "E:\powermill-ai\data\forums" mkdir "E:\powermill-ai\data\forums"

echo.
echo [2/6] Сохраняю переменные окружения (setx)...
setx POWERMILL_DATA_ROOT "E:\powermill-ai" >nul
setx OLLAMA_MODELS "E:\ollama_models" >nul
setx HF_HOME "E:\hf_cache" >nul
setx PIP_CACHE_DIR "E:\pip_cache" >nul
echo       POWERMILL_DATA_ROOT = E:\powermill-ai
echo       OLLAMA_MODELS       = E:\ollama_models
echo       HF_HOME             = E:\hf_cache
echo       PIP_CACHE_DIR       = E:\pip_cache

echo.
echo [3/6] Создаю виртуальное окружение...
if exist "venv\Scripts\python.exe" goto have_venv
python -m venv venv
goto venv_ready

:have_venv
echo       venv уже есть - пропускаю

:venv_ready
call venv\Scripts\activate

echo.
echo [4/6] Устанавливаю зависимости (torch ~2 ГБ, может занять 10-20 минут)...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto pip_partial

echo.
echo [5/6] Проверяю Ollama...
goto ollama

:pip_partial
echo.
echo [!] Часть библиотек не установилась.
echo     Если это pytorch - запусти отдельно: scripts\install_torch.bat
echo     Затем подготовь отчёт: scripts\make_report.bat
echo.

:ollama
echo.
echo [5/6] Проверяю Ollama...
set "OLLAMA_CMD="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_CMD=ollama"
if defined OLLAMA_CMD goto ollama_found
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if defined OLLAMA_CMD goto ollama_found
set "PF86=%ProgramFiles(x86)%"
if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
if defined OLLAMA_CMD goto ollama_found
if exist "%PF86%\Ollama\ollama.exe" set "OLLAMA_CMD=%PF86%\Ollama\ollama.exe"

if not defined OLLAMA_CMD goto ollama_missing
goto ollama_found

:ollama_missing
echo       [!] Ollama не найдена. Скачай: https://ollama.com/download/windows
echo           Если уже установлена - открой НОВОЕ окно и запусти setup.bat снова.
goto step6

:ollama_found
echo       Ollama найдена: %OLLAMA_CMD%

:step6
echo.
echo [6/6] Состояние базы знаний...
python -m scripts.base_status

echo.
echo =========================================================
echo   УСТАНОВКА ЗАВЕРШЕНА
echo.
echo   Дальше - всё через меню:   start_menu.bat
echo.
echo   Порядок действий:
echo     1. Скачать модели Ollama:   пункт 14 меню
echo     2. Подключить ИИ по API:    пункт 21 меню (умнее, если есть ключ)
echo     3. Проверить справку:       пункт 9 меню
echo     4. Разобрать справку:       пункт 4 меню
echo     5. Собрать векторную базу:  пункт 6 меню
echo     6. Общаться:                пункт 1 меню
echo =========================================================
echo.
pause
exit /b 0

:no_python
echo [!] Python не найден!
echo     Установи с https://www.python.org/downloads/
echo     При установке отметь галочку "Add Python to PATH".
echo.
pause
exit /b 1

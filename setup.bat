@echo off
chcp 65001 >nul
title PowerMill AI Setup (heavy data on disk E)
echo =========================================================
echo   PowerMill AI - Setup. Everything heavy goes to disk E.
echo   Code:      E:\powermill
echo   Models:    E:\ollama_models
echo   HF cache:  E:\hf_cache
echo   Pip cache: E:\pip_cache
echo =========================================================
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python not found! Install from https://www.python.org/downloads/
    echo     Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo.
echo [1/5] Creating folders on disk E...
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

echo.
echo [2/5] Saving environment variables (setx)...
setx POWERMILL_DATA_ROOT "E:\powermill" >nul
setx OLLAMA_MODELS "E:\ollama_models" >nul
setx HF_HOME "E:\hf_cache" >nul
setx PIP_CACHE_DIR "E:\pip_cache" >nul
echo       POWERMILL_DATA_ROOT = E:\powermill
echo       OLLAMA_MODELS       = E:\ollama_models
echo       HF_HOME             = E:\hf_cache
echo       PIP_CACHE_DIR       = E:\pip_cache

echo.
echo [3/5] Creating virtual environment on E: ...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
) else (
    echo       venv already exists - skipping
)
call venv\Scripts\activate

echo.
echo [4/5] Installing dependencies (torch ~2 GB, pip cache on E:)...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [5/5] Checking Ollama...
set "OLLAMA_CMD="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_CMD=ollama"
if not defined OLLAMA_CMD if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
set "PF86=%ProgramFiles(x86)%"
if not defined OLLAMA_CMD if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_CMD if exist "%PF86%\Ollama\ollama.exe" set "OLLAMA_CMD=%PF86%\Ollama\ollama.exe"

if not defined OLLAMA_CMD (
    echo [!] Ollama not found in PATH or default folders.
    echo     Download: https://ollama.com/download/windows
    echo     If already installed - open a NEW cmd window and
    echo     run setup.bat again.
) else (
    echo       Ollama found: %OLLAMA_CMD%
    echo       Next step: restart Ollama from tray, then run
    echo       start_download_models.bat
)

echo.
echo =========================================================
echo   SETUP FINISHED
echo   1. Put PDF files into E:\powermill\data\pdf
echo   2. Optional: videos into E:\powermill\data\videos
echo   3. Optional: *.mac macros into E:\powermill\data\macros
echo   4. Download models: start_download_models.bat
echo   5. Night indexing:  start_night_indexing.bat
echo   6. Chat:            start_work_chat.bat
echo =========================================================
pause

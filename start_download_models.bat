@echo off
chcp 65001 >nul
title PowerMill AI - Download Ollama models to disk E
cd /d "%~dp0"

set "OLLAMA_MODELS=E:\ollama_models"
if not exist "E:\ollama_models" mkdir "E:\ollama_models"

rem --- Find ollama.exe: PATH first, then default install folders ---
set "OLLAMA_CMD="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_CMD=ollama"
if not defined OLLAMA_CMD if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
set "PF86=%ProgramFiles(x86)%"
if not defined OLLAMA_CMD if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_CMD if exist "%PF86%\Ollama\ollama.exe" set "OLLAMA_CMD=%PF86%\Ollama\ollama.exe"

if not defined OLLAMA_CMD (
    echo [!] ollama.exe not found in PATH or default folders.
    echo     Download: https://ollama.com/download/windows
    echo     If already installed - open a NEW cmd window and run this again.
    pause
    exit /b 1
)

echo Ollama CLI:  %OLLAMA_CMD%
echo Models dir:  %OLLAMA_MODELS%
echo.
echo =========================================================
echo   IMPORTANT: restart Ollama before downloading!
echo   The running Ollama server remembers OLLAMA_MODELS
echo   from the moment it started. If you do not restart it,
echo   models will be saved to disk C by mistake.
echo.
echo   1. Right-click Ollama icon in tray -^> Quit
echo   2. Start Ollama from Start menu
echo   3. Come back here and press a key
echo =========================================================
pause

echo.
echo [1/2] qwen2.5:3b - chat model (~2 GB)...
"%OLLAMA_CMD%" pull qwen2.5:3b

echo.
echo [2/2] qwen2.5-coder:3b - PML macro model (~2 GB)...
"%OLLAMA_CMD%" pull qwen2.5-coder:3b

echo.
echo =========================================================
echo   Checking that models landed on disk E...
dir /b /a "E:\ollama_models" 2>nul | findstr /r "." >nul
if errorlevel 1 (
    echo [!] E:\ollama_models is still EMPTY.
    echo     The Ollama server was probably not restarted
    echo     and saved models to C instead.
    echo.
    echo     Fix: Quit Ollama from tray, start it again,
    echo     run this script once more. Then move leftovers:
    echo     robocopy "%USERPROFILE%\.ollama\models" "E:\ollama_models" /E /MOVE
) else (
    echo OK! Files in E:\ollama_models:
    dir /b "E:\ollama_models"
    echo.
    echo   List models:
)
"%OLLAMA_CMD%" list
echo.
echo   Start chat with: start_work_chat.bat
echo =========================================================
pause

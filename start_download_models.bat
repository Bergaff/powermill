@echo off
chcp 65001 >nul
title PowerMill AI - Download Ollama models to disk E
cd /d "%~dp0"

set "OLLAMA_MODELS=E:\ollama_models"
set "OLLAMA_HOST=http://127.0.0.1:11434"
if not exist "E:\ollama_models" mkdir "E:\ollama_models"

rem --- Never proxy localhost ---
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="
set "NO_PROXY=127.0.0.1,localhost"

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
    pause
    exit /b 1
)

echo Ollama CLI:  %OLLAMA_CMD%
echo Models dir:  %OLLAMA_MODELS%
echo.

rem --- Make sure Ollama tray app is running ---
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | findstr /I "ollama.exe" >nul
if errorlevel 1 (
    echo Starting Ollama tray app...
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    )
)

echo Waiting for server http://127.0.0.1:11434 (up to 60 sec)...
set READY=0
set /a TRIES=0
:waitloop
timeout /t 3 /nobreak >nul
set /a TRIES+=1
"%OLLAMA_CMD%" list >nul 2>nul
if not errorlevel 1 (
    set READY=1
    goto ready
)
if %TRIES% GEQ 20 goto notready
echo   still waiting... (%TRIES%)
goto waitloop

:ready
echo Server is UP. Starting downloads.
echo.

echo [1/2] qwen2.5:3b - chat model (~2 GB)...
"%OLLAMA_CMD%" pull qwen2.5:3b
if errorlevel 1 (
    echo.
    echo [!] pull qwen2.5:3b failed - retrying once...
    timeout /t 5 /nobreak >nul
    "%OLLAMA_CMD%" pull qwen2.5:3b
)

echo.
echo [2/2] qwen2.5-coder:3b - PML macro model (~2 GB)...
"%OLLAMA_CMD%" pull qwen2.5-coder:3b
if errorlevel 1 (
    echo.
    echo [!] pull qwen2.5-coder:3b failed - retrying once...
    timeout /t 5 /nobreak >nul
    "%OLLAMA_CMD%" pull qwen2.5-coder:3b
)

echo.
echo =========================================================
echo   Checking that models landed on disk E...
dir /b /a "E:\ollama_models" 2>nul | findstr /r "." >nul
if errorlevel 1 (
    echo [!] E:\ollama_models is still EMPTY.
    echo     Run scripts\fix_ollama.bat and try again.
) else (
    echo OK! Content of E:\ollama_models:
    dir /b "E:\ollama_models"
    echo.
    echo   Model list:
)
"%OLLAMA_CMD%" list
echo.
echo   Start chat with: start_work_chat.bat
echo =========================================================
pause
exit /b 0

:notready
echo.
echo =========================================================
echo   SERVER DID NOT START IN 60 SECONDS
echo =========================================================
echo Run this first:  scripts\fix_ollama.bat
echo Then check log:  %LOCALAPPDATA%\Ollama\server.log
echo Browser test:    http://127.0.0.1:11434
echo =========================================================
pause
exit /b 1

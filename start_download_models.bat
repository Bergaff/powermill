@echo off
chcp 65001 >nul
title PowerMill AI - Download 7B models to disk E
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

rem --- Find ollama.exe ---
set "OLLAMA_CMD="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_CMD=ollama"
if not defined OLLAMA_CMD if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
set "PF86=%ProgramFiles(x86)%"
if not defined OLLAMA_CMD if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_CMD if exist "%PF86%\Ollama\ollama.exe" set "OLLAMA_CMD=%PF86%\Ollama\ollama.exe"

if not defined OLLAMA_CMD (
    echo [!] ollama.exe not found.
    pause
    exit /b 1
)

echo Ollama CLI:  %OLLAMA_CMD%
echo Models dir:  %OLLAMA_MODELS%
echo.

rem --- Start tray app if needed ---
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
set /a TRIES=0
:waitloop
timeout /t 3 /nobreak >nul
set /a TRIES+=1
"%OLLAMA_CMD%" list >nul 2>nul
if not errorlevel 1 goto ready
if %TRIES% GEQ 20 goto notready
echo   still waiting... (%TRIES%)
goto waitloop

:ready
echo Server is UP. Downloading 7B models (~4.7 GB each).
echo RTX 3060 12GB handles them easily.
echo.

echo [1/2] qwen2.5:7b - chat model (~4.7 GB)...
"%OLLAMA_CMD%" pull qwen2.5:7b
if errorlevel 1 (
    echo [!] failed - retrying once...
    timeout /t 5 /nobreak >nul
    "%OLLAMA_CMD%" pull qwen2.5:7b
)

echo.
echo [2/2] qwen2.5-coder:7b - PML macro model (~4.7 GB)...
"%OLLAMA_CMD%" pull qwen2.5-coder:7b
if errorlevel 1 (
    echo [!] failed - retrying once...
    timeout /t 5 /nobreak >nul
    "%OLLAMA_CMD%" pull qwen2.5-coder:7b
)

echo.
echo =========================================================
echo   Switching chat to 7B models (saved permanently)...
setx LLM_MODEL "qwen2.5:7b" >nul
setx LLM_CODE_MODEL "qwen2.5-coder:7b" >nul
echo       LLM_MODEL      = qwen2.5:7b
echo       LLM_CODE_MODEL = qwen2.5-coder:7b
echo.
echo   Model list:
"%OLLAMA_CMD%" list
echo.
echo =========================================================
echo   IMPORTANT: close this cmd window and open a NEW one,
echo   then run:  start_work_chat.bat
echo   (setx changes are visible only to NEW windows)
echo =========================================================
pause
exit /b 0

:notready
echo.
echo [!] SERVER DID NOT START IN 60 SECONDS
echo     Run scripts\fix_ollama.bat first, then this again.
pause
exit /b 1

@echo off
chcp 65001 >nul
title Fix Ollama server (restart + health check)

set "OLLAMA_MODELS=E:\ollama_models"
set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not exist "%OLLAMA_EXE%" set "OLLAMA_EXE=ollama"

echo =========================================================
echo   1. Stopping ALL Ollama processes...
echo =========================================================
taskkill /IM ollama.exe /F >nul 2>nul
taskkill /IM ollama_app.exe /F >nul 2>nul
taskkill /IM "ollama app.exe" /F >nul 2>nul
taskkill /IM ollama_llama_server.exe /F >nul 2>nul
taskkill /IM "Ollama Windows Assistant.exe" /F >nul 2>nul
timeout /t 3 /nobreak >nul

echo.
echo =========================================================
echo   2. Port 11434 check (must be empty ^= free)
echo =========================================================
netstat -ano | findstr :11434 | findstr LISTENING
echo.

echo =========================================================
echo   3. Starting server with OLLAMA_MODELS=E:\ollama_models
echo =========================================================
if not exist "E:\ollama_models" mkdir "E:\ollama_models"
start "Ollama" /min "%OLLAMA_EXE%" serve

echo Waiting for server (up to 20 seconds)...
set READY=0
set /a TRIES=0
:waitloop
timeout /t 2 /nobreak >nul
set /a TRIES+=1
"%OLLAMA_EXE%" list >nul 2>nul
if not errorlevel 1 (
    set READY=1
    goto ready
)
if %TRIES% GEQ 10 goto failed
goto waitloop

:ready
echo.
echo =========================================================
echo   SERVER IS UP
echo =========================================================
"%OLLAMA_EXE%" list
echo.
echo Models folder: E:\ollama_models
echo.
echo Next step: run start_download_models.bat
echo (answer the restart question with a key press)
echo =========================================================
pause
exit /b 0

:failed
echo.
echo =========================================================
echo   SERVER STILL NOT STARTING
echo =========================================================
echo Last log lines, if any:
echo --- %LOCALAPPDATA%\Ollama\server.log ---
if exist "%LOCALAPPDATA%\Ollama\server.log" (
    powershell -Command "Get-Content -Tail 30 '%LOCALAPPDATA%\Ollama\server.log'"
)
echo --- %LOCALAPPDATA%\Ollama\logs\*.log ---
if exist "%LOCALAPPDATA%\Ollama\logs" dir /b /o-d "%LOCALAPPDATA%\Ollama\logs"
echo.
echo Checklist:
echo   1. Start "Ollama" from Start menu and check tray icon
echo   2. Open http://127.0.0.1:11434 in browser
echo   3. In Ollama settings the model folder must be exactly:
echo      E:\ollama_models
echo   4. Temporarily disable antivirus check on E:\ollama_models
echo   5. Reboot Windows once - sometimes only reboot clears it
echo =========================================================
pause
exit /b 1

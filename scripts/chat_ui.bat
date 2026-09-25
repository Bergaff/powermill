@echo off
chcp 65001 >nul
title PowerMill AI - интерфейс ассистента (чат в браузере)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.chat_ui --open %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Окно интерфейса закрыто. Открыть снова: scripts\chat_ui.bat (или пункт 32 меню).
pause >nul
exit /b 0

:failed
echo [!] Интерфейс не запустился (код %RC%).
echo     Что делать: пункт 32 ещё раз, при повторе — проверить порт 8765
echo     (его мог занять другой интерфейс) или посмотреть логи: пункт 19.
echo.
pause
exit /b 1

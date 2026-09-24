@echo off
chcp 65001 >nul
title PowerMill AI - мост Python к PowerMill
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.install_bridge
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo [!] Мост не встал (код %RC%).
echo     Подробности в логе: scripts\show_logs.bat
echo.
pause
exit /b 1

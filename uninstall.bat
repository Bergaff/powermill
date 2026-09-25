@echo off
chcp 65001 >nul
title PowerMill AI - удаление
cd /d "%~dp0"
echo =========================================================
echo   УДАЛЕНИЕ PowerMill AI
echo =========================================================
echo.
echo Уберу ярлыки и отменю регистрацию плагина (если он собран).
echo Данные (справка, отчёты, базы) НЕ удаляю — они в отдельной папке.
echo.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

"%PY%" -m scripts.uninstall_app %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
pause >nul
exit /b 0

:failed
echo [!] Удаление закончилось с кодом %RC% — смотри текст выше.
echo.
pause
exit /b 1

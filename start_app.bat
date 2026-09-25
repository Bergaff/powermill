@echo off
chcp 65001 >nul
title PowerMill AI - окно приложения
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo Открываю окно PowerMill AI...
"%PY%" -m src.app_window %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
exit /b 0

:failed
echo.
echo [!] Окно не открылось (код %RC%).
echo     Что делать: запусти install.bat (он поставит всё заново),
echo     либо проверь компьютер пунктом 40 меню.
echo     Если Python ставился без галочки «tcl/tk» — переустанови Python.
echo.
pause
exit /b 1

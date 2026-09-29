@echo off
chcp 65001 >nul
title PowerMill AI - проверка компьютера
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.doctor
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto notready
echo Проверка закончена: компьютер готов.
pause >nul
exit /b 0

:notready
echo [!] Проверка нашла проблемы (код %RC%) — смотри список выше.
echo     Отчёт: output\doctor_report.txt (пункт 29 меню — открыть в блокноте).
echo     Этот отчёт можно целиком прислать в чат.
echo.
pause
exit /b 1

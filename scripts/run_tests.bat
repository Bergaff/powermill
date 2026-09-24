@echo off
chcp 65001 >nul
title PowerMill AI - тесты
cd /d "%~dp0.."

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

echo =========================================================
echo   ТЕСТЫ (синтетическая справка, без ИИ и без Ollama)
echo   Проверяют также батники: переводы строк, метки, chcp
echo =========================================================
echo.
"%PY%" -m pytest tests -q
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo [OK] Все тесты прошли.
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo [!] Тесты не прошли. Подготовь отчёт: scripts\make_report.bat
echo.
pause
exit /b 1

@echo off
chcp 65001 >nul
title PowerMill AI - чему учить ассистента (правила и уроки)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.knowledge
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
exit /b 0

:failed
echo [!] Пункт завершился с ошибкой (код %RC%).
echo     Что проверить: Python установлен (пункт 12 меню); папка данных доступна
echo     (пункт 42); файл output\logs\knowledge.log.
echo.
pause
exit /b 1

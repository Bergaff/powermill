@echo off
chcp 65001 >nul
title PowerMill AI - "сказал: делай" (план -> выполнение -> проверки -> NC)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.make_flow
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт — пункт 29 меню (pm_flow_report.txt).
pause >nul
exit /b 0

:failed
echo [!] Поток остановился (код %RC%).
echo     Что делать: смотри отчёт пункта 29 (pm_flow_report.txt) — там видно,
echo     какой шаг не прошёл; строки с крестиком и пришли в чат.
echo.
pause
exit /b 1

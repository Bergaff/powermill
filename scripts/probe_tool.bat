@echo off
chcp 65001 >nul
title PowerMill AI - фреза в проект (и рабочее слово)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.probe_tool
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт — пункт 29 меню (pm_tool_report.txt).
pause >nul
exit /b 0

:failed
echo [!] Фреза не создалась (код %RC%).
echo     Что делать: проверь, что PowerMill запущен с открытым проектом,
echo     и пришли отчёт пункта 29 (pm_tool_report.txt) в чат.
echo.
pause
exit /b 1

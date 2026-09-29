@echo off
chcp 65001 >nul
title PowerMill AI - сборка плагина-панели внутри PowerMill
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.build_plugin
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт — пункт 29 меню (pm_plugin_build_report.txt).
pause >nul
exit /b 0

:failed
echo [!] Плагин не собрался или не зарегистрировался (код %RC%).
echo     Что делать: открой отчёт пунктом 29 (pm_plugin_build_report.txt) и
echo     пришли его текст в чат вместе с выводом консоли выше.
echo.
pause
exit /b 1

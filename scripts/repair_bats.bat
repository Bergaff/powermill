@echo off
chcp 65001 >nul
title PowerMill AI - починка батников
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
"%PY%" -m scripts.repair_bats
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto problems
if not defined PM_FROM_MENU pause
exit /b 0

:problems
echo [!] Замечания по батникам выше. Если это про переводы строк —
echo     запусти этот пункт ещё раз (он уже исправил) и пришли отчёт.
echo.
pause
exit /b 1

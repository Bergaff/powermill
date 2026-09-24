@echo off
chcp 65001 >nul
title PowerMill AI - диагностика справки
cd /d "%~dp0.."

echo =========================================================
echo   ДИАГНОСТИКА СПРАВКИ: что реально лежит в Help
echo   Образцы файлов сохраняются в output\help_samples
echo =========================================================
echo.

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

"%PY%" -m scripts.dump_help_samples
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed

echo.
echo =========================================================
echo   Скопируй ВЕСЬ вывод выше и пришли в чат.
echo   Образцы файлов лежат в: output\help_samples
echo =========================================================
if not defined PM_FROM_MENU pause
exit /b 0

:failed
echo.
echo [!] Ошибка. Проверь, что задан путь к справке:
echo     POWERMILL_HELP_DIR = C:\ProgramData\Autodesk\PowerMill\2026\Help
echo     Задать путь: пункт 10 меню (scripts\set_help_path.bat)
echo.
pause
exit /b 1

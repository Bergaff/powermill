@echo off
chcp 65001 >nul
title Find PowerMill offline HTML help
cd /d "%~dp0\.."

echo =========================================================
echo   Ищу оффлайн-справку PowerMill и показываю её структуру
echo =========================================================
echo.

set "VENV=.venv\Scripts"
if not exist "%VENV%\python.exe" set "VENV=venv\Scripts"
if exist "%VENV%\python.exe" set "PATH=%CD%\%VENV%;%PATH%"
if not exist "%VENV%\python.exe" echo [!] Виртуального окружения нет - работаю системным Python - поставь install.bat

python -m scripts.dump_help_samples
echo.
echo =========================================================
echo   Если справка не найдена, укажи путь руками:
echo     setx POWERMILL_HELP_DIR "C:\ProgramData\Autodesk\PowerMill\2026\Help"
echo     (после setx открой НОВОЕ окно cmd)
echo =========================================================
pause

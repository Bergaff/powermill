@echo off
chcp 65001 >nul
title PowerMill AI - dump help samples (diagnostics)
cd /d "%~dp0\.."

echo =========================================================
echo   ДИАГНОСТИКА СПРАВКИ: что реально лежит в Help
echo   Образцы файлов сохраняются в output\help_samples
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Виртуального окружения нет - работаю системным Python.
    echo     Если чего-то не хватает - запусти setup_light.bat (1 минута)
    echo.
)

python -m scripts.dump_help_samples
if errorlevel 1 (
    echo.
    echo [!] Ошибка. Проверь, что задан путь:
    echo     set POWERMILL_HELP_DIR=C:\ProgramData\Autodesk\PowerMill\2026\Help
    pause
    exit /b 1
)

echo.
echo =========================================================
echo   Скопируй ВЕСЬ вывод выше и пришли в чат.
echo   Образцы файлов лежат в: output\help_samples
echo =========================================================
pause

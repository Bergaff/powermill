@echo off
chcp 65001 >nul
title Find PowerMill offline HTML help
cd /d "%~dp0\.."

echo =========================================================
echo   Ищу оффлайн-справку PowerMill и показываю её структуру
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] venv не найден - работаю системным Python
)

python -m scripts.dump_help_samples
echo.
echo =========================================================
echo   Если справка не найдена, укажи путь руками:
echo     setx POWERMILL_HELP_DIR "C:\ProgramData\Autodesk\PowerMill\2026\Help"
echo     (после setx открой НОВОЕ окно cmd)
echo =========================================================
pause

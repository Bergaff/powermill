@echo off
chcp 65001 >nul
title PowerMill AI - путь к справке PowerMill
cd /d "%~dp0\.."

echo =========================================================
echo   ПУТЬ К ОФФЛАЙН-СПРАВКЕ PowerMill
echo =========================================================
echo.
echo   Обычно это: C:\ProgramData\Autodesk\PowerMill\2026\Help
echo   (внутри должна быть папка l.rus или l.enu)
echo.
echo   Скопируй нужный путь и вставь его ниже (правый клик = вставка).
echo.

set "PMHELP="
set /p PMHELP="Путь к папке Help (Enter - отмена): "
if not defined PMHELP (
    echo Отмена.
    pause
    exit /b 0
)

if not exist "%PMHELP%\" (
    echo.
    echo [!] Такой папки нет: %PMHELP%
    pause
    exit /b 1
)

if not exist "%PMHELP%\l.rus\" if not exist "%PMHELP%\l.enu\" (
    echo.
    echo [!] Внутри нет папок l.rus / l.enu.
    echo     Похоже, это не папка справки. Проверь путь.
    pause
    exit /b 1
)

setx POWERMILL_HELP_DIR "%PMHELP%" >nul
echo.
echo =========================================================
echo   ГОТОВО. Путь сохранён навсегда:
echo     POWERMILL_HELP_DIR = %PMHELP%
echo.
echo   ВАЖНО: переменная видна только в НОВЫХ окнах cmd.
echo   Закрой это окно и запусти start_menu.bat снова.
echo =========================================================
echo.
pause

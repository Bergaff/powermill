@echo off
chcp 65001 >nul
title PowerMill AI - разбор справки PowerMill
set APP_MODE=turbo
cd /d "%~dp0"

echo =========================================================
echo   РАЗБОР СПРАВКИ PowerMill
echo   Текст берётся из files\*.htm И из wrapped-files\*.js
echo   (там, где он на самом деле лежит)
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Виртуального окружения нет - работаю системным Python.
    echo     Если чего-то не хватает - запусти setup_light.bat (1 минута)
    echo.
)

python -m scripts.preflight parse
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)
echo.

rem Пробный запуск:  start_parse_help.bat 30
if not "%~1"=="" (
    echo [ПРОБНЫЙ ЗАПУСК] разбираю только %~1 страниц...
    python -m src.html_parser --limit %~1
) else (
    echo [1/2] Полный разбор справки (обычно 1-3 минуты)...
    python -m src.html_parser
)

if errorlevel 1 (
    echo.
    echo [!] Разбор не удался. Подготовь отчёт и пришли в чат:
    echo        scripts\make_report.bat
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Собираю индекс быстрого поиска (SQLite FTS5)...
python -m src.help_search --rebuild
if errorlevel 1 (
    echo [!] Не удалось собрать индекс поиска
    pause
    exit /b 1
)

echo.
python -m scripts.base_status

echo.
echo =========================================================
echo   ГОТОВО.
echo   Страницы:  output\help_pages.jsonl
echo   Дерево:    output\help_toc.txt
echo   Отчёт:     output\help_report.txt
echo.
echo   Проверить поиск (без ИИ):
echo      start_help_search.bat
echo   Собрать векторную базу:
echo      start_reindex_help.bat
echo =========================================================
if not "%~1"=="" (
    echo.
    echo Открываю отчёт разбора...
    start "" notepad "output\help_report.txt"
)
pause

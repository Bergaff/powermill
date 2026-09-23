@echo off
chcp 65001 >nul
title PowerMill AI - parse offline Help
set APP_MODE=turbo
cd /d "%~dp0"

echo =========================================================
echo   РАЗБОР СПРАВКИ PowerMill (offline Help + PML reference)
echo   Текст берётся из files\*.htm И из wrapped-files\*.js
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] venv не найден - запусти setup.bat
    pause
    exit /b 1
)

rem Быстрая проверка на 30 страницах:  start_parse_help.bat 30
if not "%~1"=="" (
    echo [ПРОБНЫЙ ЗАПУСК] парсю только %~1 страниц...
    python -m src.html_parser --limit %~1
) else (
    echo [1/2] Полный разбор справки (может занять пару минут)...
    python -m src.html_parser
    if errorlevel 1 (
        echo [!] Разбор не удался - смотри сообщения выше
        pause
        exit /b 1
    )
)

echo.
echo [2/2] Индекс быстрого поиска (SQLite FTS5)...
python -m src.help_search --rebuild

echo.
echo =========================================================
echo   ГОТОВО. Отчёт: output\help_report.txt
echo   Дерево тем:   output\help_toc.txt
echo   Страницы:     output\help_pages.jsonl
echo.
echo   Проверить поиск без запуска чата:
echo     python -m src.help_search "чистовая обработка по кривой"
echo.
echo   Дальше: start_reindex_help.bat  (собрать векторную базу)
echo =========================================================
if not "%~1"=="" (
    echo.
    echo Открываю отчёт...
    start "" notepad "output\help_report.txt"
)
pause

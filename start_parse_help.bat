@echo off
chcp 65001 >nul
title PowerMill AI - разбор справки
set APP_MODE=turbo
setlocal
cd /d "%~dp0"

echo =========================================================
echo   РАЗБОР СПРАВКИ PowerMill
echo   Текст берётся из files\*.htm и из wrapped-files\*.js
echo   Весь вывод пишется в  output\logs\parse_help.log
echo =========================================================
echo.

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo [!] Виртуального окружения нет - работаю системным Python.
echo     Если чего-то не хватает: setup_light.bat - 1 минута
echo.
:venv_ok

set "LIMIT=%~1"
if not "%LIMIT%"=="" echo Режим ПРОБЫ: разбираю только %LIMIT% страниц
echo Подожди, идёт работа...
echo.

if "%LIMIT%"=="" goto full_parse
"%PY%" -m src.html_parser --limit %LIMIT%
goto after_parse

:full_parse
"%PY%" -m src.html_parser

:after_parse
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto parse_failed
echo [ГОТОВО] Разбор справки завершён.
goto index_step

:parse_failed
echo [!] РАЗБОР НЕ УДАЛСЯ, код ошибки %RC%
echo.
echo --- Последние строки лога ---
powershell -NoProfile -Command "if (Test-Path 'output\logs\parse_help.log') { Get-Content -Tail 25 'output\logs\parse_help.log' } else { 'лог не найден' }"
echo ----------------------------
echo.
echo Что делать:
echo   1) Проверь папку справки:  пункт 9 меню
echo   2) Нет venv - запусти:     setup_light.bat
echo   3) Пришли в чат файл:      output\logs\parse_help.log
echo.
pause
exit /b 1

:index_step
echo.
echo Собираю индекс быстрого поиска...
"%PY%" -m src.help_search --rebuild
if not "%ERRORLEVEL%"=="0" goto index_failed
echo.
"%PY%" -m scripts.base_status
echo.
echo =========================================================
echo   ГОТОВО
echo   Страницы: output\help_pages.jsonl
echo   Дерево:   output\help_toc.txt
echo   Отчёт:    output\help_report.txt
echo.
echo   Дальше: пункт 2 меню - поиск по справке
echo =========================================================
echo.
if "%LIMIT%"=="" goto finish
echo ПРОБА ЗАВЕРШЕНА: база пока неполная.
echo   Повтори пункт 4 меню - БЕЗ числа, тогда справка разберётся целиком.
echo.
echo Открываю отчёт разбора...
if exist "output\help_report.txt" start "" notepad "output\help_report.txt"
goto finish

:index_failed
echo.
echo [!] Разбор прошёл, но индекс поиска не собрался.
echo     Пришли в чат: output\logs\help_search.log
echo.

:finish
pause
exit /b 0

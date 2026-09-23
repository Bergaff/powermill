@echo off
chcp 65001 >nul
title PowerMill AI [ECO - рабочий чат]
cd /d "%~dp0"

echo =========================================================
echo   PowerMill AI - чат с ассистентом (режим ECO, днём)
echo   * приоритет ниже среднего - PowerMill не тормозит
echo   * VRAM освобождается сразу после ответа
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение не найдено.
    echo     Запусти setup.bat (один раз), затем start_menu.bat
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate

python -m scripts.preflight chat
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo.
echo =========================================================
echo   Команды чата:
echo     вопрос по-русски        - ответ по документации
echo     /macro задача           - сгенерировать PML-макрос
echo     /cutting материал фреза - режимы резания
echo     /error текст ошибки     - разбор ошибки
echo     /compare A и B          - сравнение стратегий
echo     /sources запрос         - что нашлось в базе
echo     /stats                  - состав базы знаний
echo     /help                   - все команды
echo     /exit                   - выход
echo =========================================================
echo.

python -m src.rag

echo.
echo Чат завершён. Вернуться в меню: start_menu.bat
pause

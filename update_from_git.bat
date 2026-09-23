@echo off
chcp 65001 >nul
title PowerMill AI - обновление программы из Git
cd /d "%~dp0"

echo =========================================================
echo   ОБНОВЛЕНИЕ PowerMill AI (свежая версия из GitHub)
echo =========================================================
echo.

if not exist ".git\" (
    echo [!] Это не папка репозитория - запусти батник из E:\powermill-ai
    echo.
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo [!] Git не установлен.
    echo     Скачай: https://git-scm.com/download/win
    echo     Потом запусти этот батник снова.
    echo.
    pause
    exit /b 1
)

echo Текущая версия:
git log -1 --oneline

echo.
echo Есть ли у тебя несохранённые правки?
git status --short
echo (пусто выше = правок нет, всё в порядке)

echo.
echo [1/3] Забираю свежие данные с GitHub...
git fetch origin
if errorlevel 1 (
    echo.
    echo [!] Нет связи с GitHub. Проверь интернет или VPN, затем повтори.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/3] Переключаюсь на рабочую ветку...
git checkout arena/01a0ce77-powermill
if errorlevel 1 (
    echo.
    echo    Ветки нет локально - создаю из GitHub...
    git checkout -B arena/01a0ce77-powermill origin/arena/01a0ce77-powermill
    if errorlevel 1 (
        echo.
        echo [!] Не удалось переключить ветку.
        echo     Если выше написано про незакоммиченные изменения:
        echo     сохрани их или запусти scripts\make_report.bat и пришли отчёт в чат.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo [3/3] Обновляю файлы...
git pull --ff-only
if errorlevel 1 (
    echo.
    echo [!] Автоматическое обновление не прошло (правки в файлах?).
    echo     Ничего не потеряно - старые файлы на месте.
    echo     Подготовь отчёт и пришли в чат: scripts\make_report.bat
    echo.
    pause
    exit /b 1
)

echo.
echo =========================================================
echo   ОБНОВЛЕНО. Теперь версия такая:
git log -1 --oneline
echo =========================================================
echo.
echo   Дальше: start_menu.bat
echo.
pause

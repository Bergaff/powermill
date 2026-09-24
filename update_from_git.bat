@echo off
chcp 65001 >nul
title PowerMill AI - обновление из GitHub
cd /d "%~dp0"

echo =========================================================
echo   ОБНОВЛЕНИЕ PowerMill AI (свежая версия из GitHub)
echo =========================================================
echo.

if not exist ".git\" goto no_git_folder

where git >nul 2>nul
if errorlevel 1 goto no_git

echo Текущая версия:
git log -1 --oneline

echo.
echo Есть ли несохранённые правки?
git status --short
echo (пусто выше = правок нет, всё в порядке)

echo.
echo [1/3] Забираю свежие данные с GitHub...
git fetch origin
if errorlevel 1 goto no_network

echo.
echo [2/3] Переключаюсь на рабочую ветку...
git checkout arena/01a0ce77-powermill
if not errorlevel 1 goto branch_ready

echo.
echo    Ветки нет локально - создаю из GitHub...
git checkout -B arena/01a0ce77-powermill origin/arena/01a0ce77-powermill
if errorlevel 1 goto branch_failed

:branch_ready
echo.
echo [3/3] Обновляю файлы...
git pull --ff-only
if errorlevel 1 goto pull_failed

echo.
echo [Проверка] Починяю переводы строк в батниках (в Windows они должны быть CRLF)...
python -m scripts.repair_bats
echo.

echo =========================================================
echo   ОБНОВЛЕНО. Теперь версия такая:
git log -1 --oneline
echo =========================================================
echo.
echo   Дальше: start_menu.bat
echo.
if not defined PM_FROM_MENU pause
exit /b 0

:no_git_folder
echo [!] Это не папка репозитория.
echo     Запусти батник из E:\powermill-ai (там, где лежит .git).
echo.
pause
exit /b 1

:no_git
echo [!] Git не установлен.
echo     Скачай: https://git-scm.com/download/win
echo     Потом запусти этот батник снова.
echo.
pause
exit /b 1

:no_network
echo.
echo [!] Нет связи с GitHub. Проверь интернет или VPN, затем повтори.
echo.
pause
exit /b 1

:branch_failed
echo.
echo [!] Не удалось переключить ветку.
echo     Если выше написано про незакоммиченные изменения:
echo     подготовь отчёт (пункт 13 меню) и пришли в чат.
echo.
pause
exit /b 1

:pull_failed
echo.
echo [!] Автоматическое обновление не прошло (правки в файлах?).
echo     Ничего не потеряно - старые файлы на месте.
echo     Подготовь отчёт и пришли в чат: пункт 13 меню.
echo.
pause
exit /b 1

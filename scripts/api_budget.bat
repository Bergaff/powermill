@echo off
chcp 65001 >nul
title PowerMill AI - расходы на ИИ и лимиты
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
:menu
set "ARGS="
set "action="
echo.
echo ============================================================
echo   РАСХОДЫ НА ИИ И ЛИМИТЫ (облачный API, пункт 46)
echo ============================================================
echo   Облачный ИИ (DeepSeek, OpenAI, OpenRouter...) стоит денег за каждый
echo   токен, поэтому расход считается, а лимиты держат его в границах.
echo   Когда лимит исчерпан, запрос к платному сервису НЕ уходит - приходит
echo   объяснение и подсказка перейти на бесплатную локальную модель (пункт 22).
echo.
echo   1 - показать расходы и лимиты
echo   2 - поменять лимиты (запросы в день, деньги в день и в месяц, токены)
echo   3 - сделать отчёт по дням (файл, его можно прислать в чат)
echo   4 - обнулить счётчики (лимиты и ключ не трогаются)
echo   0 - назад
echo.
set /p action="   Выбор (0-4): "
if "%action%"=="0" exit /b 0
if "%action%"=="1" set "ARGS=--show"
if "%action%"=="2" set "ARGS=--set"
if "%action%"=="3" set "ARGS=--report"
if "%action%"=="4" set "ARGS=--reset"
if not defined ARGS goto bad_choice
echo.
"%PY%" -m scripts.api_budget %ARGS%
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
if "%action%"=="3" echo Отчёт лежит здесь: output\api_spend_report.txt (он же в пункте 29 меню)
echo Назад в это меню - любая клавиша.
pause >nul
goto menu

:bad_choice
echo   Не понял выбор. Введи цифру от 0 до 4.
goto menu

:failed
echo [!] Не получилось показать расходы (код %RC%).
echo     Пришли этот текст в чат. Логи: scripts\show_logs.bat
echo.
pause
exit /b 1

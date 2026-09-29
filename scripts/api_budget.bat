@echo off
chcp 65001 >nul
title PowerMill AI - расходы на ИИ и лимиты
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo Облачный ИИ (DeepSeek, OpenAI, OpenRouter...) стоит денег за каждый токен.
echo Здесь видно, сколько уже израсходовано, и ставятся границы: запросы в день,
echo деньги в день и в месяц, потолок токенов на ответ.
echo.
echo Когда лимит исчерпан, запрос к платному сервису НЕ уходит - приходит
echo объяснение и подсказка переключиться на бесплатную локальную модель (пункт 22).
echo.
"%PY%" -m scripts.api_budget
set "RC=%ERRORLEVEL%"
echo.
echo Поменять лимиты: этот же пункт с ключом --set, например
echo   "%PY%" -m scripts.api_budget --set
echo Отчёт по дням: output\api_spend_report.txt (пункт 29 меню).
echo.
if not "%RC%"=="0" goto failed
pause
exit /b 0

:failed
echo [!] Не получилось показать расходы (код %RC%).
echo     Пришли этот текст в чат. Логи: scripts\show_logs.bat
echo.
pause
exit /b 1

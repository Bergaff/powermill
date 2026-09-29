@echo off
chcp 65001 >nul
title PowerMill AI - связка с PowerMill
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo ============================================================
echo   СВЯЗКА С POWERMILL (пункт 47)
echo   мост (пункт 27) -^> макросы (пункт 28) -^> проверка делом (пункт 41)
echo ============================================================
echo.
echo   PowerMill лучше открыть заранее - с проектом: связка проверит его
echo   делом (PowerMill выполнит наш макрос и запишет файл-отметку).
echo   Проект при этом не меняется.
echo.
"%PY%" -m scripts.link_setup
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto not_yet
echo [OK] Связь работает: PowerMill выполнил нашу команду.
echo     Отчёт: output\pm_link_setup_report.txt (можно прислать в чат).
echo.
pause
exit /b 0

:not_yet
echo [!] Связь пока не подтвердилась (код %RC%).
echo     Это не поломка: в отчёте выше видно, на каком шаге PowerMill
echo     не ответил, и что делать. Отчёт: output\pm_link_setup_report.txt
echo     Логи: scripts\show_logs.bat
echo.
pause
exit /b 1

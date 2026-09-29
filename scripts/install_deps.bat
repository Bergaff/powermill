@echo off
chcp 65001 >nul
title PowerMill AI - доставить нужные библиотеки
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo Ставлю недостающие библиотеки в тот же Python, из которого работает программа:
echo   %PY%
echo.
"%PY%" -m scripts.install_deps
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт: output\install_packages_report.txt (пункт 29 меню).
echo [Нажми любую клавишу, чтобы вернуться в меню]
pause >nul
exit /b 0

:failed
echo [!] Не всё поставилось (код %RC%).
echo     Чаще всего это интернет или pip. Отчёт: output\install_packages_report.txt
echo     Подробности в логе: scripts\show_logs.bat
echo.
pause
exit /b 1

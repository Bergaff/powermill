@echo off
chcp 65001 >nul
title PowerMill AI - установка для нового компьютера
cd /d "%~dp0"
echo =========================================================
echo   УСТАНОВКА PowerMill AI
echo   Поставит программу, библиотеки и ярлыки.
echo =========================================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto no_python

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto old_python

rem Если окружение уже создано, дальше работаем его Python
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

%PY% "scripts\install_app.py" %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Установка закончена. Ярлык «PowerMill AI» — на рабочем столе.
pause >nul
exit /b 0

:no_python
echo [!] Python не найден.
echo     Скачай Python 3.12 с https://www.python.org/downloads/
echo     Важно: при установке поставь галочку «Add python.exe to PATH».
echo     Потом запусти install.bat снова.
echo.
echo     Если Python уже стоит, но не виден: переустанови его с галочкой PATH.
pause
exit /b 2

:old_python
echo [!] Python слишком старый (нужен 3.10 или новее).
echo     Скачай новый: https://www.python.org/downloads/
pause
exit /b 2

:failed
echo [!] Установка остановилась (код %RC%).
echo     Отчёт: install_report.txt рядом с install.bat — пришли его в чат.
echo.
pause
exit /b 1

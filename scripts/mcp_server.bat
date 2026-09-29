@echo off
chcp 65001 >nul
title PowerMill AI - MCP-сервер (проверка)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo Этот сервер запускает сам ИИ-клиент (Claude, Cursor, VS Code) - ему
echo передаётся настройка из пункта 44. Здесь две проверки:
echo   1) что сервер умеет и не сломан (в этом же процессе);
echo   2) что клиент его получит - сервер запускается отдельным процессом
echo      и отвечает по стандартному вводу-выводу, как это делает клиент.
echo.
"%PY%" -m scripts.mcp_server --selftest
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
"%PY%" -m scripts.mcp_server --probe
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Подключить клиент: пункт 44 меню (scripts\mcp_setup.bat).
echo Отчёт: output\mcp_report.txt (пункт 29 меню).
echo Список инструментов целиком: пункт 45, вторая проверка.
echo.
pause
exit /b 0

:failed
echo [!] Самопроверка MCP-сервера не прошла (код %RC%).
echo     Пришли её текст в чат - по нему видно, что сломалось.
echo     Логи: scripts\show_logs.bat
echo.
pause
exit /b 1

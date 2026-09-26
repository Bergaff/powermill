@echo off
chcp 65001 >nul
title PowerMill AI - MCP-сервер (проверка)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo Этот сервер запускает сам ИИ-клиент (Claude, Cursor, VS Code) - ему
echo передаётся настройка из пункта 44. Двойным щелчком полезнее проверка:
echo что сервер умеет и не сломан ли он.
echo.
"%PY%" -m scripts.mcp_server --selftest
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Список инструментов целиком: "%PY%" -m scripts.mcp_server --tools
echo Подключить клиент: пункт 44 меню (scripts\mcp_setup.bat).
echo Отчёт: output\mcp_report.txt (пункт 29 меню).
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

@echo off
chcp 65001 >nul
title PowerMill AI - подключение к ИИ-клиенту (MCP)
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo Подключение к ИИ-клиенту по MCP: в чате Claude / Cursor / VS Code появятся
echo инструменты PowerMill AI - режимы резания, разбор ошибок, план операции,
echo состояние PowerMill.
echo.
echo Чужие настройки не перезаписываются: сначала делается копия .bak,
echo наш сервер добавляется к уже прописанным.
echo.
"%PY%" -m scripts.mcp_setup
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto failed
echo Готово. Отчёт: output\mcp_report.txt (пункт 29 меню).
echo Перезапусти ИИ-клиент, чтобы он увидел инструменты.
echo.
pause
exit /b 0

:failed
echo [!] Подключить не получилось (код %RC%).
echo     Отчёт: output\mcp_report.txt - пришли его в чат.
echo     Блок настроек можно вставить в клиент вручную: "%PY%" -m scripts.mcp_setup --show
echo.
pause
exit /b 1

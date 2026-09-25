@echo off
chcp 65001 >nul
title PowerMill AI [ECO - рабочий чат]
set APP_MODE=eco
setlocal
cd /d "%~dp0"

echo =========================================================
echo   PowerMill AI - чат с ассистентом, режим ECO
echo   Приоритет ниже среднего: PowerMill не тормозит
echo =========================================================
echo.

set "VENV=.venv\Scripts"
if not exist "%VENV%\python.exe" set "VENV=venv\Scripts"
if not exist "%VENV%\python.exe" goto no_venv
set "PATH=%CD%\%VENV%;%PATH%"
echo   Python: %CD%\%VENV%\python.exe

python -m scripts.preflight chat
if errorlevel 1 goto failed

echo   Команды чата:
echo     обычный вопрос          - ответ по документации
echo     /macro задача           - сгенерировать PML-макрос
echo     /cutting материал фреза - режимы резания
echo     /error текст ошибки     - разбор ошибки
echo     /compare A и B          - сравнение стратегий
echo     /sources запрос         - что нашлось в базе
echo     /stats                  - состав базы знаний
echo     /help                   - все команды
echo     назад или меню          - выход в главное меню
echo.
python -m src.rag
echo.
echo Чат завершён.
echo.
if not defined PM_FROM_MENU pause
exit /b 0

:no_venv
echo [!] Нет виртуального окружения (ни .venv, ни venv).
echo     Запусти install.bat - он создаст .venv и поставит библиотеки.
echo     Библиотеки те же, что и программе: пункт 43 меню.
echo.
pause
exit /b 1

:failed
echo.
echo [!] Чат не запущен - смотри сообщения выше.
echo.
pause
exit /b 1

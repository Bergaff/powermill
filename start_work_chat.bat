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

if not exist "venv\Scripts\python.exe" goto no_venv
call venv\Scripts\activate

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
echo     /exit                   - выход
echo.
python -m src.rag
echo.
echo Чат завершён. Вернуться в меню: start_menu.bat
echo.
pause
exit /b 0

:no_venv
echo [!] Нет виртуального окружения.
echo     Полная установка:  setup.bat
echo     Без ИИ, быстро:    setup_light.bat
echo.
pause
exit /b 1

:failed
echo.
echo [!] Чат не запущен - смотри сообщения выше.
echo.
pause
exit /b 1

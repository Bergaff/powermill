@echo off
chcp 65001 >nul
title PowerMill AI - быстрая установка (разбор справки + поиск)
cd /d "%~dp0"

echo =========================================================
echo   БЫСТРАЯ УСТАНОВКА  (1-2 минуты, интернет нужен)
echo.
echo   Ставит только то, что нужно для:
echo     * разбора справки PowerMill
echo     * поиска по справке (без ИИ)
echo     * калькулятора режимов резания
echo.
echo   ИИ (Ollama), векторная база и видео НЕ ставятся -
echo   их можно добавить позже полным setup.bat.
echo =========================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto no_python

echo [1/3] Виртуальное окружение...
if exist "venv\Scripts\python.exe" goto have_venv
python -m venv venv
goto venv_ready

:have_venv
echo       venv уже есть - пропускаю

:venv_ready
call venv\Scripts\activate

echo.
echo [2/3] Ставлю лёгкие библиотеки (beautifulsoup4, tqdm, psutil, pytest)...
python -m pip install --upgrade pip --quiet
pip install --quiet beautifulsoup4 tqdm psutil pytest
if errorlevel 1 goto pip_failed

echo.
echo [3/3] Проверяю...
python -c "import bs4, tqdm, psutil; print('   библиотеки на месте')"

echo.
echo =========================================================
echo   ГОТОВО. Дальше по шагам:
echo     1) start_menu.bat  -^>  пункт 9   (что лежит в справке)
echo     2) start_menu.bat  -^>  пункт 4   (разобрать справку)
echo     3) start_menu.bat  -^>  пункт 2   (поиск по справке)
echo     4) start_menu.bat  -^>  пункт 3   (режимы резания)
echo =========================================================
echo.
pause
exit /b 0

:no_python
echo [!] Python не найден!
echo     Установи с https://www.python.org/downloads/
echo     При установке отметь "Add Python to PATH".
echo.
pause
exit /b 1

:pip_failed
echo.
echo [!] Не удалось установить библиотеки. Проверь интернет и повтори.
echo     Если ошибка про SSL или прокси - проверь настройки сети.
echo.
pause
exit /b 1

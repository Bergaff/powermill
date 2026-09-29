@echo off
chcp 65001 >nul
title PowerMill AI - установка pytorch (если не влез)
cd /d "%~dp0.."

echo =========================================================
echo   УСТАНОВКА pytorch для эмбеддингов
echo   Нужен, если setup.bat не смог скачать torch (~2.5 ГБ).
echo   Кэш pip должен лежать на E: (scripts\set_heavy_paths.bat).
echo =========================================================
echo.

set "VENV=.venv\Scripts"
if not exist "%VENV%\python.exe" set "VENV=venv\Scripts"
if not exist "%VENV%\python.exe" goto no_venv
set "PATH=%CD%\%VENV%;%PATH%"
echo   Python: %CD%\%VENV%\python.exe

if defined PIP_CACHE_DIR goto have_cache
set "PIP_CACHE_DIR=E:\pip_cache"
echo    pip cache -^> %PIP_CACHE_DIR%

:have_cache
echo.
echo [1/3] Обновляю pip...
python -m pip install --upgrade pip

echo.
echo [2/3] Ставлю torch (CPU-версия, меньше размер)...
pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto torch_failed

echo.
echo [3/3] Проверяю импорт...
python -c "import torch; print('torch', torch.__version__, 'OK')"
if errorlevel 1 goto import_failed

echo.
echo =========================================================
echo   ГОТОВО. Теперь: start_menu.bat -^> пункт 6 (векторная база)
echo =========================================================
if not defined PM_FROM_MENU pause
exit /b 0

:no_venv
echo [!] Нет виртуального окружения (ни .venv, ни venv).
echo     Запусти install.bat - он создаст .venv и поставит библиотеки.
echo     Библиотеки те же, что и программе: пункт 43 меню.
echo.
pause
exit /b 1

:torch_failed
echo.
echo [!] Не получилось. Проверь:
echo     1) интернет и свободное место на E:
echo     2) CPU-версия меньше: pip install torch --index-url https://download.pytorch.org/whl/cpu
echo.
pause
exit /b 1

:import_failed
echo [!] torch скачался, но не импортируется.
echo     Подготовь отчёт и пришли в чат: scripts\make_report.bat
echo.
pause
exit /b 1

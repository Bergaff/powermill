
@echo off
chcp 65001 >nul
title PowerMill AI - установка pytorch (если не влез)
cd /d "%~dp0\.."

echo =========================================================
echo   УСТАНОВКА pytorch для эмбеддингов
echo   Нужен, если setup.bat не смог скачать torch (~2.5 ГБ).
echo   Кэш pip должен лежать на E: (проверь scripts\set_heavy_paths.bat).
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate
) else (
    echo [!] Нет venv - сначала setup.bat
    pause
    exit /b 1
)

if not defined PIP_CACHE_DIR (
    set "PIP_CACHE_DIR=E:\pip_cache"
    echo    pip cache -> %PIP_CACHE_DIR%
)

echo.
echo [1/3] Обновляю pip...
python -m pip install --upgrade pip

echo.
echo [2/3] Ставлю torch (CPU-версия, меньше размер)...
pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo.
    echo [!] Не получилось. Варианты:
    echo     1) проверь интернет и свободное место на E:
    echo     2) CPU-версия меньше: pip install torch --index-url https://download.pytorch.org/whl/cpu
    pause
    exit /b 1
)

echo.
echo [3/3] Проверяю импорт...
python -c "import torch; print('torch', torch.__version__, 'OK')"
if errorlevel 1 (
    echo [!] torch не импортируется
    pause
    exit /b 1
)

echo.
echo =========================================================
echo   ГОТОВО. Теперь: start_reindex_help.bat
echo =========================================================
pause

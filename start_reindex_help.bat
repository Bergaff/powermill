@echo off
chcp 65001 >nul
title PowerMill AI - векторная база
set APP_MODE=turbo
setlocal
cd /d "%~dp0"

echo =========================================================
echo   СБОРКА ВЕКТОРНОЙ БАЗЫ ChromaDB на диске E:
echo   Долго: эмбеддинги на CPU, 10-60 минут.
echo   Лучше на ночь: start_night_indexing.bat
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" goto no_venv
call venv\Scripts\activate

python -m scripts.preflight reindex
if errorlevel 1 goto failed

echo.
echo Начинаю. Не выключай компьютер. Прервать - Ctrl+C.
echo.
python -m src.vectorstore
if errorlevel 1 goto build_failed

echo.
python -m scripts.base_status
echo.
echo =========================================================
echo   ГОТОВО. Общаться с ассистентом: пункт 1 меню
echo =========================================================
echo.
pause
exit /b 0

:no_venv
echo [!] Нет venv - запусти setup.bat
echo     Быстрый старт без ИИ: setup_light.bat
echo.
pause
exit /b 1

:failed
echo.
echo [!] Не всё готово для сборки - смотри сообщения выше.
echo.
pause
exit /b 1

:build_failed
echo.
echo [!] Сборка не удалась.
echo     Если ошибка про torch - запусти scripts\install_torch.bat
echo     Лог: output\logs\vectorstore.log
echo.
pause
exit /b 1

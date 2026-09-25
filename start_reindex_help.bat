@echo off
chcp 65001 >nul
title PowerMill AI - векторная база
set APP_MODE=turbo
setlocal
cd /d "%~dp0"

echo =========================================================
echo   ВЕКТОРНАЯ БАЗА (ChromaDB): смысловой поиск по справке
echo   Долго: эмбеддинги на CPU, 10-60 минут. Лучше на ночь.
echo   Прервать можно - следующий запуск продолжит с места остановки.
echo   Нет библиотек? Сначала пункт 43 (доставить, ключ --all).
echo =========================================================
echo.

set "VENV=.venv\Scripts"
if not exist "%VENV%\python.exe" set "VENV=venv\Scripts"
if not exist "%VENV%\python.exe" goto no_venv
set "PATH=%CD%\%VENV%;%PATH%"
echo   Python: %CD%\%VENV%\python.exe

python -m scripts.preflight reindex
if errorlevel 1 goto failed

echo.
echo Начинаю. Не выключай компьютер. Прервать - Ctrl+C.
echo.
python -m src.vectorstore
if errorlevel 2 goto no_libs
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

:no_libs
echo.
echo [!] Нет библиотек для векторной базы (chromadb / sentence-transformers).
echo     Поставить: start_menu.bat -^> 43 (ключ --all) - это несколько
echo     гигабайт, лучше ночью. Потом снова запусти этот пункт.
echo     Отчёт: output\vector_db_report.txt
echo.
pause
exit /b 2

:no_venv
echo [!] Нет виртуального окружения (ни .venv, ни venv).
echo     Запусти install.bat - он создаст .venv и поставит библиотеки.
echo     Библиотеки те же, что и программе: пункт 43 меню.
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

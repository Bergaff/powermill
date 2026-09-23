@echo off
chcp 65001 >nul
title PowerMill AI - пересборка векторной базы
set APP_MODE=turbo
cd /d "%~dp0"

echo =========================================================
echo   ПЕРЕСБОРКА ВЕКТОРНОЙ БАЗЫ (ChromaDB на диске E:)
echo   Долго: эмбеддинги считаются на CPU (~10-60 минут).
echo   Лучше запускать ночью или через start_night_indexing.bat
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение не найдено - запусти setup.bat
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate

python -m scripts.preflight reindex
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo.
echo Начинаю. Не выключай компьютер. Прервать - Ctrl+C.
echo.

python -m src.vectorstore
if errorlevel 1 (
    echo.
    echo [!] Пересборка не удалась.
    echo     Если ошибка про torch - запусти scripts\install_torch.bat
    echo     Подготовить отчёт: scripts\make_report.bat
    echo.
    pause
    exit /b 1
)

echo.
python -m scripts.base_status
echo.
echo =========================================================
echo   ГОТОВО. Общаться с ассистентом: start_work_chat.bat
echo =========================================================
pause

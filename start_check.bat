@echo off
chcp 65001 >nul
title PowerMill AI - проверка установки
cd /d "%~dp0"

echo =========================================================
echo   ПРОВЕРКА УСТАНОВКИ
echo   Python, зависимости, папки на E:, Ollama, тесты
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    echo [1/5] venv найден: venv\Scripts\python.exe
    call venv\Scripts\activate
) else (
    echo [1/5] [!] venv НЕ найден - запусти setup.bat
    echo.
    pause
    exit /b 1
)

echo.
echo [2/5] Версия Python:
python --version

echo.
echo [3/5] Проверка библиотек...
python -c "import sys; mods=['bs4','tqdm','psutil','chromadb','sentence_transformers','ollama','faster_whisper','aiogram','langchain_text_splitters']; miss=[m for m in mods if __import__('importlib').util.find_spec(m) is None]; print('OK: все библиотеки на месте' if not miss else 'НЕ ХВАТАЕТ: '+', '.join(miss)); sys.exit(1 if miss else 0)"
if errorlevel 1 (
    echo     Исправление: pip install -r requirements.txt
    echo     Подсказка: scripts\install_torch.bat - если не влез pytorch
)

echo.
echo [4/5] Папки на диске E:
python -c "from config import PDF_DIR, VIDEO_DIR, MACRO_DIR, CHROMA_DIR, OUTPUT_DIR, HELP_DIR, DATA_ROOT; import pathlib; [print(f'   {p}  (есть: {p.exists()})') for p in (DATA_ROOT, PDF_DIR, VIDEO_DIR, MACRO_DIR, OUTPUT_DIR, CHROMA_DIR)]; print(f'   справка: {HELP_DIR}  (есть: {HELP_DIR.exists()})')"

echo.
echo [5/5] Тесты (79 штук, справка-образец, без ИИ):
python -m pytest tests -q
if errorlevel 1 (
    echo.
    echo [!] Тесты не прошли. Подготовь отчёт: scripts\make_report.bat
    echo.
    pause
    exit /b 1
)

echo.
echo =========================================================
echo   ВСЁ В ПОРЯДКЕ. Дальше:
echo     1. start_parse_help.bat        - разобрать справку
echo     2. start_reindex_help.bat      - собрать векторную базу
echo     3. start_work_chat.bat         - общаться с ассистентом
echo =========================================================
echo.
pause

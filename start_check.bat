@echo off
chcp 65001 >nul
title PowerMill AI - проверка установки
cd /d "%~dp0"

echo =========================================================
echo   ПРОВЕРКА УСТАНОВКИ
echo   Python, библиотеки, папки на E:, Ollama, тесты
echo =========================================================
echo.

if not exist "venv\Scripts\python.exe" goto no_venv
echo [1/6] venv найден: venv\Scripts\python.exe
call venv\Scripts\activate
goto step2

:no_venv
echo [1/6] venv НЕ найден - работаю системным Python.
echo       Если что-то не установлено, запусти setup.bat
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
goto step2

:step2
echo.
echo [2/6] Версия Python:
python --version

echo.
echo [3/6] Проверка библиотек...
python -c "import sys; mods=['bs4','tqdm','psutil','chromadb','sentence_transformers','ollama','faster_whisper','aiogram','langchain_text_splitters']; miss=[m for m in mods if __import__('importlib').util.find_spec(m) is None]; print('OK: все библиотеки на месте' if not miss else 'НЕ ХВАТАЕТ: '+', '.join(miss)); sys.exit(1 if miss else 0)"
if errorlevel 1 goto libs_missing
goto step4

:libs_missing
echo     Пропущенные библиотеки нужны только для векторного поиска и чата.
echo     Исправление: pip install -r requirements.txt
echo     Не влез pytorch: scripts\install_torch.bat
echo.

:step4
echo [4/6] Папки на диске E:
python -c "from config import PDF_DIR, VIDEO_DIR, MACRO_DIR, CHROMA_DIR, OUTPUT_DIR, HELP_DIR, DATA_ROOT; [print(f'   {p}  (есть: {p.exists()})') for p in (DATA_ROOT, PDF_DIR, VIDEO_DIR, MACRO_DIR, OUTPUT_DIR, CHROMA_DIR)]; print(f'   справка: {HELP_DIR}  (есть: {HELP_DIR.exists()})')"

echo.
echo [5/6] ИИ (мозг ассистента):
python -m src.llm --test
echo.
echo     Если ИИ не отвечает - пункт 21 меню подключает облачный ИИ по API,
echo     пункт 22 переключает между локальной моделью и API.

echo.
echo [6/6] Тесты (быстрые, без ИИ):
python -m pytest tests -q
if errorlevel 1 goto tests_failed
goto done

:tests_failed
echo.
echo [!] Тесты не прошли. Подготовь отчёт: scripts\make_report.bat
echo.
if not defined PM_FROM_MENU pause
exit /b 1

:done
echo.
echo =========================================================
echo   ВСЁ В ПОРЯДКЕ. Дальше:
echo     1. start_parse_help.bat        - разобрать справку (пункт 4 меню)
echo     2. start_reindex_help.bat      - собрать векторную базу (пункт 6)
echo     3. start_work_chat.bat         - общаться с ассистентом (пункт 1)
echo =========================================================
echo.
if not defined PM_FROM_MENU pause
exit /b 0

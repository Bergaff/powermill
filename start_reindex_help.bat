@echo off
chcp 65001 >nul
title PowerMill AI - Reindex offline Help
cd /d "%~dp0"
call venv\Scripts\activate

echo =========================================================
echo   Parse offline HTML Help + PML reference
echo   and rebuild ChromaDB on disk E.
echo =========================================================
echo.

echo [1/2] Parsing HTML help...
python -m src.html_parser
if errorlevel 1 (
    echo [!] html_parser failed
    pause
    exit /b 1
)

echo.
echo [2/2] Rebuilding vector store...
python -m src.vectorstore
if errorlevel 1 (
    echo [!] vectorstore failed
    pause
    exit /b 1
)

echo.
echo =========================================================
echo   DONE. Start chat:  start_work_chat.bat
echo   Test inside chat:
echo     /sources tool selection
echo     /sources Offset Area Clearance
echo =========================================================
pause

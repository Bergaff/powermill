@echo off
chcp 65001 >nul
title PowerMill AI [TURBO - night indexing]
set APP_MODE=turbo
echo =======================================================
echo   PowerMill AI - TURBO MODE (run at night)
echo   * Maximum CPU power
echo   * Builds knowledge base on disk E
echo =======================================================
cd /d "%~dp0"
call venv\Scripts\activate

echo [1/5] Parsing PDF files from E:\powermill-ai\data\pdf ...
python -m src.pdf_parser
if errorlevel 1 echo    (skipped or error - continuing)

echo.
echo [2/5] Parsing local HTML help (PML parameter reference)...
python -m src.html_parser
if errorlevel 1 echo    (no help folder or error - continuing)

echo.
echo [3/5] Scraping online help help.autodesk.com (if needed)...
if exist "E:\powermill-ai\output\parsed_web.txt" (
    echo    parsed_web.txt already exists - skip. Delete it to re-scrape.
) else (
    python -m src.web_scraper
    if errorlevel 1 echo    (scrape failed - continuing with local data)
)

echo.
echo [4/5] Transcribing videos from E:\powermill-ai\data\videos (if any)...
python -m src.video_parser
if errorlevel 1 echo    (no videos or error - continuing)

echo.
echo [5/5] Building ChromaDB vector store on E:\powermill-ai\chroma_db ...
python -m src.vectorstore

echo.
echo =======================================================
echo   DONE! Now you can run start_work_chat.bat
echo =======================================================
pause

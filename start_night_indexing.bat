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

echo [1/4] Parsing PDF files from E:\powermill-ai\data\pdf ...
python -m src.pdf_parser
if errorlevel 1 echo    (skipped or error - continuing)

echo.
echo [2/4] Parsing offline HTML Help + PML reference...
python -m src.html_parser
if errorlevel 1 echo    (no help folder or error - continuing)

echo.
echo [3/4] Transcribing videos from E:\powermill-ai\data\videos (if any)...
python -m src.video_parser
if errorlevel 1 echo    (no videos or error - continuing)

echo.
echo [4/4] Building ChromaDB vector store on E:\powermill-ai\chroma_db ...
python -m src.vectorstore

echo.
echo =======================================================
echo   DONE! Now you can run start_work_chat.bat
echo =======================================================
pause

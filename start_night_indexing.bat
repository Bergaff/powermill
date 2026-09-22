@echo off
chcp 65001 >nul
title PowerMill AI [TURBO - night indexing]
set APP_MODE=turbo
echo =======================================================
echo   PowerMill AI - TURBO MODE (run at night)
echo   * Maximum CPU power
echo   * VRAM stays loaded between steps
echo =======================================================
cd /d "%~dp0"
call venv\Scripts\activate

echo [1/3] Parsing PDF files from E:\powermill\data\pdf ...
python -m src.pdf_parser
if errorlevel 1 echo    (skipped or error - continuing)

echo.
echo [2/3] Transcribing videos from E:\powermill\data\videos (if any)...
python -m src.video_parser
if errorlevel 1 echo    (no videos or error - continuing)

echo.
echo [3/3] Building ChromaDB vector store on E:\powermill\chroma_db ...
python -m src.vectorstore

echo.
echo =======================================================
echo   DONE! Now you can run start_work_chat.bat
echo =======================================================
pause

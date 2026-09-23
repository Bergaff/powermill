@echo off
chcp 65001 >nul
title PowerMill AI - Scrape online help (help.autodesk.com)
cd /d "%~dp0"
call venv\Scripts\activate

echo =========================================================
echo   Downloading PowerMill 2026 online help articles
echo   from help.autodesk.com into knowledge base.
echo.
echo   * ~500 pages, 0.4 sec pause between requests
echo   * Progress is saved - Ctrl+C and run again to resume
echo   * Result: E:\powermill-ai\output\parsed_web.txt
echo =========================================================
echo.

pip show requests >nul 2>nul
if errorlevel 1 pip install requests beautifulsoup4

python -m src.web_scraper

echo.
echo =========================================================
echo   Rebuilding vector store with new articles...
python -m src.vectorstore
echo.
echo   DONE. Run start_work_chat.bat and try:
echo     /sources Offset Area Clearance
echo =========================================================
pause

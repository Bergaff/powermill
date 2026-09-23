@echo off
chcp 65001 >nul
title PowerMill AI - Scrape online help (help.autodesk.com)
cd /d "%~dp0"
call venv\Scripts\activate

echo =========================================================
echo   Downloading PowerMill 2026 online help articles
echo   from help.autodesk.com into knowledge base.
echo.
echo   * curl_cffi impersonates Chrome TLS - bypasses HTTP 403
echo   * ~500 pages, pause between requests
echo   * Progress saved - Ctrl+C and run again to resume
echo   * Result: E:\powermill-ai\output\parsed_web.txt
echo =========================================================
echo.

echo [1/2] Installing HTTP libraries...
pip install -q curl_cffi requests beautifulsoup4

echo [2/2] Scraping...
python -m src.web_scraper

if not exist "E:\powermill-ai\output\parsed_web.txt" goto fail
for %%A in ("E:\powermill-ai\output\parsed_web.txt") do if %%~zA LSS 100 goto fail

echo.
echo =========================================================
echo   Rebuilding vector store with new articles...
python -m src.vectorstore
echo.
echo   DONE. Run start_work_chat.bat and try:
echo     /sources Offset Area Clearance
echo =========================================================
pause
exit /b 0

:fail
echo.
echo =========================================================
echo   Scraping produced no articles.
echo   1. Check messages above (403 or empty SPA)
echo   2. Try: del output\web_scrape_state.json  and run again
echo   3. Or install OFFLINE help:
echo      https://www.autodesk.com/powermill-2026-help-download-enu
echo      then: scripts\find_help.bat  +  set POWERMILL_HELP_DIR=...
echo      then: start_night_indexing.bat
echo =========================================================
pause
exit /b 1

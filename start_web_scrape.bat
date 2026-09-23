@echo off
chcp 65001 >nul
title PowerMill AI - Scrape online help (help.autodesk.com)
cd /d "%~dp0"
call venv\Scripts\activate

echo =========================================================
echo   Downloading PowerMill help articles into knowledge base.
echo   * direct fetch with Chrome TLS (curl_cffi)
echo   * on HTTP 403: automatic Wayback Machine fallback
echo   * result: E:\powermill-ai\output\parsed_web.txt
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
echo   No articles downloaded.
echo   OFFLINE HELP (most reliable):
echo     https://www.autodesk.com/powermill-2026-help-download-enu
echo     scripts\find_help.bat
echo     set POWERMILL_HELP_DIR=E:\path\to\offline\help
echo     start_night_indexing.bat
echo =========================================================
pause
exit /b 1

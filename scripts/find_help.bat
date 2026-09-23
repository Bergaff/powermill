@echo off
chcp 65001 >nul
title Find PowerMill HTML help on this PC
echo =========================================================
echo   Looking for local PowerMill 2026 HTML documentation...
echo =========================================================

echo.
echo [1] Count of HTML files in main install tree (may take a moment):
dir /s /b "E:\powermill 2026\PowerMill 2026\*.htm" 2>nul > "%TEMP%\pm_html_list.txt"
dir /s /b "E:\powermill 2026\PowerMill 2026\*.html" 2>nul >> "%TEMP%\pm_html_list.txt"
for %%F in ("%TEMP%\pm_html_list.txt") do echo       found: %%~zF bytes in list

echo.
echo [2] Top-level folders of the install:
dir /b /ad "E:\powermill 2026\PowerMill 2026" 2>nul

echo.
echo [3] lib\locale contents (docs usually live here):
dir /b /ad "E:\powermill 2026\PowerMill 2026\lib\locale" 2>nul
dir /b /ad "E:\powermill 2026\PowerMill 2026\lib\locale\C" 2>nul

echo.
echo [4] Known doc entry points:
dir /b "E:\powermill 2026\PowerMill 2026\lib\locale\C\PARSUM" 2>nul
dir /b "E:\powermill 2026\PowerMill 2026\lib\locale\C\PARREF" 2>nul

echo.
echo [5] First 30 HTML paths found (full list in %TEMP%\pm_html_list.txt):
powershell -Command "Get-Content -Head 30 '%TEMP%\pm_html_list.txt'" 2>nul

echo.
echo =========================================================
echo   Next: set POWERMILL_HELP_DIR to the folder that
echo   CONTAINS the docs (the one with index.html / parameters.html)
echo   and run:  python -m src.html_parser
echo =========================================================
pause

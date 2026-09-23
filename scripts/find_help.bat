@echo off
chcp 65001 >nul
title Find PowerMill offline HTML help
echo =========================================================
echo   Looking for PowerMill 2026 offline documentation...
echo =========================================================

echo.
echo [1] Offline help (ProgramData):
dir /b "C:\ProgramData\Autodesk\PowerMill\2026\Help" 2>nul
echo     --- l.rus ---
dir /b "C:\ProgramData\Autodesk\PowerMill\2026\Help\l.rus" 2>nul | more +0
dir /s /b "C:\ProgramData\Autodesk\PowerMill\2026\Help\*.html" 2>nul > "%TEMP%\pm_offline_help.txt"
dir /s /b "C:\ProgramData\Autodesk\PowerMill\2026\Help\*.htm" 2>nul >> "%TEMP%\pm_offline_help.txt"
for %%F in ("%TEMP%\pm_offline_help.txt") do echo       HTML files list: %%~zF bytes

echo.
echo [2] PML reference in install tree:
dir /b /ad "E:\powermill 2026\PowerMill 2026\lib\locale\C" 2>nul

echo.
echo [3] First 30 offline help paths:
powershell -Command "Get-Content -Head 30 '%TEMP%\pm_offline_help.txt'" 2>nul

echo.
echo =========================================================
echo   Defaults used by the project:
echo     C:\ProgramData\Autodesk\PowerMill\2026\Help
echo     E:\powermill 2026\PowerMill 2026\lib\locale\C
echo.
echo   Override if needed:
echo     set POWERMILL_HELP_DIR=C:\your\path
echo.
echo   Then parse and index:
echo     python -m src.html_parser
echo     python -m src.vectorstore
echo =========================================================
pause

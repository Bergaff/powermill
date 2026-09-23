@echo off
chcp 65001 >nul
title Inspect offline Help structure
set HELP=C:\ProgramData\Autodesk\PowerMill\2026\Help

echo =========================================================
echo   [1] Top-level of Help:
echo =========================================================
dir /b /a "%HELP%" 2>nul

echo.
echo =========================================================
echo   [2] Top-level of l.rus:
echo =========================================================
dir /b /a "%HELP%\l.rus" 2>nul

echo.
echo =========================================================
echo   [3] Extensions (count):
echo =========================================================
powershell -NoProfile -Command "Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue '%HELP%' | Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 20 Count,Name | Format-Table -AutoSize | Out-String -Width 120"

echo.
echo =========================================================
echo   [4] 30 largest files (full articles may be here):
echo =========================================================
powershell -NoProfile -Command "Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue '%HELP%' | Sort-Object Length -Descending | Select-Object -First 30 | ForEach-Object { '{0,10}  {1}' -f $_.Length, $_.FullName.Replace('%HELP%\','') }"

echo.
echo =========================================================
echo   [5] Also check product-wide docs:
echo =========================================================
dir /b /a "C:\ProgramData\Autodesk\PowerMill\2026" 2>nul
dir /s /b "C:\ProgramData\Autodesk\PowerMill\2026\*.pdf" 2>nul | findstr /i /c:".pdf"
dir /s /b "E:\powermill 2026\PowerMill 2026\*.pdf" 2>nul | findstr /i /c:".pdf"

echo.
echo =========================================================
echo   Paste this whole output into the chat.
echo =========================================================
pause

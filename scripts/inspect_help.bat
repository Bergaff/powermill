@echo off
chcp 65001 >nul
title Inspect Help - deep dive (files / wrapped-files / js)
set L=C:\ProgramData\Autodesk\PowerMill\2026\Help\l.rus

echo =========================================================
echo   [1] files\ - count and extensions:
echo =========================================================
dir /b /a "%L%\files" 2>nul | find /c /v ""
powershell -NoProfile -Command "if (Test-Path '%L%\files') { Get-ChildItem '%L%\files' -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Format-Table Count,Name -AutoSize | Out-String -Width 100 } else { 'NO files folder' }"

echo.
echo =========================================================
echo   [2] files\ - first 25 entries:
echo =========================================================
dir /b /a "%L%\files" 2>nul | more +0
powershell -NoProfile -Command "Get-ChildItem '%L%\files' -File -ErrorAction SilentlyContinue | Select-Object -First 25 | ForEach-Object { '{0,9}  {1}' -f $_.Length, $_.Name }"

echo.
echo =========================================================
echo   [3] wrapped-files\ - count and first 25:
echo =========================================================
powershell -NoProfile -Command "if (Test-Path '%L%\wrapped-files') { Get-ChildItem '%L%\wrapped-files' -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Format-Table Count,Name -AutoSize | Out-String -Width 100; Get-ChildItem '%L%\wrapped-files' -Recurse -File | Sort-Object Length -Descending | Select-Object -First 25 | ForEach-Object { '{0,9}  {1}' -f $_.Length, $_.FullName.Replace('%L%\','') } } else { 'NO wrapped-files folder' }"

echo.
echo =========================================================
echo   [4] contexthelp count vs other htm:
echo =========================================================
powershell -NoProfile -Command "Get-ChildItem '%L%' -Recurse -Filter *.htm | ForEach-Object { $_.Directory.Name } | Group-Object | Sort-Object Count -Descending | Select-Object -First 10 Count,Name | Format-Table -AutoSize | Out-String -Width 100"

echo.
echo =========================================================
echo   [5] SAMPLE toc-treedata.js (first 1500 chars):
echo =========================================================
powershell -NoProfile -Command "$p='%L%\scripts\toc-treedata.js'; if (Test-Path $p) { $t=[IO.File]::ReadAllText($p); if ($t.Length -gt 1500) { $t.Substring(0,1500) } else { $t } } else { 'no toc' }"

echo.
echo.
echo =========================================================
echo   [6] SAMPLE search-entries1.js (first 1500 chars):
echo =========================================================
powershell -NoProfile -Command "$p='%L%\scripts\search-entries1.js'; if (Test-Path $p) { $t=[IO.File]::ReadAllText($p); if ($t.Length -gt 1500) { $t.Substring(0,1500) } else { $t } } else { 'no search-entries1' }"

echo.
echo.
echo =========================================================
echo   [7] Any large htm OUTSIDE contexthelp (gt 2000 bytes):
echo =========================================================
powershell -NoProfile -Command "Get-ChildItem '%L%' -Recurse -Filter *.htm | Where-Object { $_.Length -gt 2000 -and $_.DirectoryName -notmatch 'contexthelp' } | Sort-Object Length -Descending | Select-Object -First 20 | ForEach-Object { '{0,9}  {1}' -f $_.Length, $_.FullName.Replace('%L%\','') }"

echo.
echo =========================================================
echo   Paste everything into chat.
echo =========================================================
pause

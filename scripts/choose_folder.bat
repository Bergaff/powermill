@echo off
chcp 65001 >nul
title PowerMill AI - папка данных
cd /d "%~dp0.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
echo.
echo Откроется окно выбора папки: куда складывать справку, базы поиска и отчёты.
echo Выбор запоминается в install.json — переменные окружения не нужны.
echo.
"%PY%" -m scripts.choose_folder
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto notchanged
echo Папка изменена. Открой окно приложения заново (или нажми «Перезапустить»).
echo Отчёт: output\data_root_report.txt (пункт 29 меню).
echo.
pause
exit /b 0

:notchanged
echo [!] Папка не изменена (код %RC%).
echo     Возможные причины: выбор отменён; в папку нельзя писать (нет прав);
echo     диск не подключён. Попробуй другую папку — например, на диске D: или
echo     в своей папке пользователя.
echo     Отчёт: output\data_root_report.txt
echo.
pause
exit /b 1

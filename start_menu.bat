@echo off
chcp 65001 >nul
title PowerMill AI - главное меню
cd /d "%~dp0"

:menu
cls
echo =========================================================
echo    🤖  PowerMill AI  —  ассистент технолога
echo =========================================================
echo.
echo    ЗАПУСК
echo      1  -  Чат с ассистентом           (ECO, днём)
echo      2  -  Поиск по справке без ИИ     (мгновенно)
echo      3  -  Калькулятор режимов резания
echo.
echo    ПОДГОТОВКА БАЗЫ ЗНАНИЙ
echo      4  -  Разобрать справку PowerMill      (полностью)
echo      5  -  Разобрать справку ПРОБНО 30 стр. (проверка)
echo      6  -  Собрать векторную базу           (долго, лучше ночью)
echo      7  -  Ночная полная индексация         (PDF+видео+справка)
echo.
echo    ДИАГНОСТИКА И НАСТРОЙКА
echo      8  -  Состояние базы знаний
echo      9  -  Что лежит в папке справки (диагностика)
echo     10  -  Найти справку на диске
echo     11  -  Указать путь к справке вручную
echo     12  -  Проверка установки (зависимости + тесты)
echo     13  -  Подготовить ОТЧЁТ для отправки в чат
echo     14  -  Скачать модели Ollama (~5 ГБ)
echo     15  -  Починить Ollama (не отвечает)
echo     16  -  Скачать pytorch (если не влез)
echo.
echo      0  -  Выход
echo.
set /p choice="   Выбор (0-16): "

if "%choice%"=="1"  goto chat
if "%choice%"=="2"  goto search
if "%choice%"=="3"  goto cutting
if "%choice%"=="4"  goto parse
if "%choice%"=="5"  goto parse30
if "%choice%"=="6"  goto reindex
if "%choice%"=="7"  goto night
if "%choice%"=="8"  goto status
if "%choice%"=="9"  goto dump
if "%choice%"=="10" goto findhelp
if "%choice%"=="11" goto setpath
if "%choice%"=="12" goto check
if "%choice%"=="13" goto report
if "%choice%"=="14" goto models
if "%choice%"=="15" goto fixollama
if "%choice%"=="16" goto torch
if "%choice%"=="0"  exit /b 0
goto menu

:chat
call "%~dp0start_work_chat.bat"
goto menu

:search
call "%~dp0start_help_search.bat"
goto menu

:cutting
call "%~dp0start_cutting.bat"
goto menu

:parse
call "%~dp0start_parse_help.bat"
goto menu

:parse30
call "%~dp0start_parse_help.bat" 30
goto menu

:reindex
call "%~dp0start_reindex_help.bat"
goto menu

:night
call "%~dp0start_night_indexing.bat"
goto menu

:status
call "%~dp0scripts\base_status.bat"
goto menu

:dump
call "%~dp0scripts\dump_help_samples.bat"
goto menu

:findhelp
call "%~dp0scripts\find_help.bat"
goto menu

:setpath
call "%~dp0scripts\set_help_path.bat"
goto menu

:check
call "%~dp0start_check.bat"
goto menu

:report
call "%~dp0scripts\make_report.bat"
goto menu

:models
call "%~dp0start_download_models.bat"
goto menu

:fixollama
call "%~dp0scripts\fix_ollama.bat"
goto menu

:torch
call "%~dp0scripts\install_torch.bat"
goto menu

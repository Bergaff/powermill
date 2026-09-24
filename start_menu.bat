@echo off
chcp 65001 >nul
title PowerMill AI - главное меню
cd /d "%~dp0"
rem Дочерние батники видят эту переменную и не делают лишнюю «паузу»:
rem после Ctrl+C или слова «меню» управление сразу возвращается сюда.
set "PM_FROM_MENU=1"

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
echo     17  -  Обновить программу из Git (git pull)
echo     18  -  Быстрая установка       (разбор+поиск, 1 минута)
echo     19  -  Логи последних запусков (если что-то не сработало)
echo     20  -  Найти макросы .mac на диске (примеры для генерации PML)
echo     21  -  Подключить ИИ по API   (умнее, нужен ключ; справка остаётся у тебя)
echo     22  -  Переключить ИИ: локальный (Ollama) или API
echo     23  -  Проверить связь с PowerMill (что доступно для плагина/приложения)
echo     24  -  Прочитать проект PowerMill живьём (или снимок макросом)
echo     25  -  Подготовить плагин PowerMill (найти каркас и инструменты сборки)
echo     26  -  Починить батники (если окно закрылось или сыпет ошибки)
echo     27  -  Поставить мост к PowerMill (живое чтение проекта)
echo     28  -  Макросы PowerMill AI внутри PowerMill (кнопка ассистента)
echo     29  -  Показать отчёты (блокнот: разведка API, макросы, снимок)
echo.
echo    ЗАПИСЬ В ПРОЕКТ (Уровень 3, по шагам)
echo     30  -  Записать режимы резания в проект PowerMill (шаг 3.1)
echo.
echo     31  -  Собрать черновую операцию (инструмент+заготовка+траектория)
echo     32  -  Интерфейс в браузере: чат, прогресс, отчёты (пункт 32)
echo.
echo     33  -  Создать фрезу в проекте PowerMill (и выяснить рабочее слово)
echo.
echo      0  -  Выход
echo.
echo   Внутри любых экранов слово  «назад»  или  «меню»
echo   возвращает к этому списку.
echo.
set /p choice="   Выбор (0-33): "

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
if "%choice%"=="17" goto update
if "%choice%"=="18" goto light
if "%choice%"=="19" goto logs
if "%choice%"=="20" goto macros
if "%choice%"=="21" goto api
if "%choice%"=="22" goto switchai
if "%choice%"=="23" goto pmlink
if "%choice%"=="24" goto project
if "%choice%"=="25" goto plugin
if "%choice%"=="26" goto repair
if "%choice%"=="27" goto bridge
if "%choice%"=="28" goto pmmacros
if "%choice%"=="29" goto reports
if "%choice%"=="30" goto apply
if "%choice%"=="31" goto operation
if "%choice%"=="32" goto webui
if "%choice%"=="33" goto protool
if "%choice%"=="0"  exit /b 0
if /i "%choice%"=="назад" exit /b 0
if /i "%choice%"=="меню" goto menu
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

:update
call "%~dp0update_from_git.bat"
goto menu

:light
call "%~dp0setup_light.bat"
goto menu

:api
call "%~dp0scripts\setup_api.bat"
goto menu

:reports
call "%~dp0scripts\show_reports.bat"
goto menu

:apply
call "%~dp0scripts\apply_cutting.bat"
goto menu

:operation
call "%~dp0scripts\make_operation.bat"
goto menu

:webui
call "%~dp0scripts\chat_ui.bat"
goto menu

:protool
call "%~dp0scripts\probe_tool.bat"
goto menu

:pmmacros
call "%~dp0scripts\prepare_pm_macros.bat"
goto menu

:bridge
call "%~dp0scripts\install_bridge.bat"
goto menu

:repair
call "%~dp0scripts\repair_bats.bat"
goto menu

:project
call "%~dp0scripts\load_project.bat"
goto menu

:plugin
call "%~dp0scripts\prepare_plugin.bat"
goto menu

:pmlink
call "%~dp0scripts\check_pm_api.bat"
goto menu

:switchai
call "%~dp0scripts\switch_ai.bat"
goto menu

:macros
call "%~dp0scripts\find_macros.bat"
goto menu

:logs
call "%~dp0scripts\show_logs.bat"
goto menu

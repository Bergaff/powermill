@echo off
chcp 65001 >nul
title PowerMill AI [ECO - рабочий режим]
set APP_MODE=eco
echo =======================================================
echo   PowerMill AI - РЕЖИМ РАБОТЫ (не грузит систему)
echo   * Приоритет CPU ниже среднего - PowerMill не лагает
echo   * VRAM освобождается сразу после каждого ответа
echo =======================================================
cd /d "%~dp0"
call venv\Scripts\activate
python -m src.rag
pause

@echo off
chcp 65001 >nul
title PowerMill AI [ECO - working mode]
set APP_MODE=eco
echo =======================================================
echo   PowerMill AI - ECO MODE (does not slow your PC)
echo   * Below-normal CPU priority: PowerMill stays smooth
echo   * VRAM is freed right after each answer
echo =======================================================
cd /d "%~dp0"
call venv\Scripts\activate
python -m src.rag
pause

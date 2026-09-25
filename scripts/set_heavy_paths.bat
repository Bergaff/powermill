@echo off
chcp 65001 >nul
title PowerMill AI - Move heavy data to disk E (permanent)
echo =========================================================
echo   Saves environment variables via setx.
echo   Run ONCE (or after Windows reinstall).
echo =========================================================

setx POWERMILL_DATA_ROOT "E:\powermill-ai"
setx OLLAMA_MODELS "E:\ollama_models"
setx HF_HOME "E:\hf_cache"
setx PIP_CACHE_DIR "E:\pip_cache"

echo.
echo DONE! Variables saved:
echo    POWERMILL_DATA_ROOT = E:\powermill-ai     (PDF, videos, ChromaDB)
echo    OLLAMA_MODELS       = E:\ollama_models (LLM models)
echo    HF_HOME             = E:\hf_cache      (embedding cache)
echo    PIP_CACHE_DIR       = E:\pip_cache     (pip cache)
echo.
echo IMPORTANT: restart Ollama (Quit in tray, then start again)
echo so it picks up OLLAMA_MODELS=E:\ollama_models.
echo.
echo If old models already downloaded to C:, move them with:
echo    robocopy "%USERPROFILE%\.ollama\models" "E:\ollama_models" /E /MOVE
pause

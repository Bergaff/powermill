@echo off
chcp 65001 >nul
title PowerMill AI - Перенос тяжёлого на диск E (навсегда)
echo =========================================================
echo   Сохраняет переменные окружения через setx.
echo   Выполни ОДИН раз (или после переустановки Windows).
echo =========================================================

setx POWERMILL_DATA_ROOT "E:\powermill"
setx OLLAMA_MODELS "E:\ollama_models"
setx HF_HOME "E:\hf_cache"
setx PIP_CACHE_DIR "E:\pip_cache"

echo.
echo ✅ Готово! Переменные сохранены:
echo    POWERMILL_DATA_ROOT = E:\powermill     (PDF, видео, ChromaDB)
echo    OLLAMA_MODELS       = E:\ollama_models (модели LLM)
echo    HF_HOME             = E:\hf_cache      (кэш эмбеддингов)
echo    PIP_CACHE_DIR       = E:\pip_cache     (кэш pip)
echo.
echo ⚠️ Перезапусти Ollama (Quit в трее → запусти заново),
echo    чтобы она подхватила OLLAMA_MODELS=E:\ollama_models.
echo.
echo Если старые модели уже скачались на C:, перемести их:
echo    robocopy "%USERPROFILE%\.ollama\models" "E:\ollama_models" /E /MOVE
pause

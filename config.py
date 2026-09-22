"""
Конфигурация проекта PowerMill AI.

Правило дисков:
  • Лёгкий код — где угодно (лучше клонировать репозиторий на E:\\powermill).
  • ВСЁ тяжёлое — только диск E:
      - данные (PDF, видео, макросы, форумы), ChromaDB, output  -> E:\\powermill
      - модели Ollama                                           -> E:\\ollama_models
      - кэш HuggingFace / SentenceTransformers                  -> E:\\hf_cache
      - кэш pip                                                 -> E:\\pip_cache
"""
import os
from pathlib import Path

# === Режим работы: eco (днём, за компом) / turbo (ночью, в полную силу) ===
CURRENT_MODE = os.getenv("APP_MODE", "eco")

# === Где лежит код репозитория ===
CODE_DIR = Path(__file__).resolve().parent

# === Корень тяжёлых данных: ТОЛЬКО диск E ===
# Переопределить можно переменной окружения POWERMILL_DATA_ROOT.
DATA_ROOT = Path(os.getenv("POWERMILL_DATA_ROOT", "E:/powermill-ai"))

DATA_DIR = DATA_ROOT / "data"
PDF_DIR = DATA_DIR / "pdf"
VIDEO_DIR = DATA_DIR / "videos"
MACRO_DIR = DATA_DIR / "macros"
FORUM_DIR = DATA_DIR / "forums"
CHROMA_DIR = DATA_ROOT / "chroma_db"
OUTPUT_DIR = DATA_ROOT / "output"

for _d in (PDF_DIR, VIDEO_DIR, MACRO_DIR, FORUM_DIR, CHROMA_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# === Модели Ollama (под 4 ГБ VRAM: RTX 3060 4GB) ===
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_CODE_MODEL = os.getenv("LLM_CODE_MODEL", "qwen2.5-coder:3b")

# Эмбеддинги — лёгкие, ~90 МБ, работают на CPU
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# === Профили производительности ===
if CURRENT_MODE == "turbo":
    # Ночной / фоновый режим: максимум ресурсов
    WHISPER_MODEL = "base"        # быстрее; поставь "small", если хватает RAM
    OLLAMA_KEEP_ALIVE = "30m"     # модель держится в VRAM между запросами
    CHUNK_SIZE = 700
    TOP_K = 5
    EMBED_BATCH_SIZE = 64
else:
    # Дневной рабочий режим: не мешаем PowerMill и браузеру
    WHISPER_MODEL = "base"
    OLLAMA_KEEP_ALIVE = "0s"      # выгрузка из VRAM сразу после ответа
    CHUNK_SIZE = 500
    TOP_K = 3
    EMBED_BATCH_SIZE = 16

CHUNK_OVERLAP = 100

# === Ollama ===
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# === Telegram ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

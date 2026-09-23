"""
Конфигурация проекта PowerMill AI.

Правило дисков:
  • Лёгкий код — где угодно (лучше клонировать репозиторий на E:\\powermill-ai).
  • ВСЁ тяжёлое — только диск E:
      - данные (PDF, видео, макросы, форумы), ChromaDB, output  -> E:\\powermill-ai
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

# === Модели Ollama ===
# 3B — минимум (уже скачаны). При 12 ГБ VRAM рекомендуется 7B:
#   ollama pull qwen2.5:7b
#   ollama pull qwen2.5-coder:7b
#   setx LLM_MODEL qwen2.5:7b
#   setx LLM_CODE_MODEL qwen2.5-coder:7b
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_CODE_MODEL = os.getenv("LLM_CODE_MODEL", "qwen2.5-coder:3b")

# Эмбеддинги — мультиязычные (русский запрос ↔ английская документация).
# ~500 МБ, кэш в E:\hf_cache, работает на CPU.
# Смена модели требует ПОЛНОЙ пересборки базы: python -m src.vectorstore
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

# === RAG ===
# Порог релевантности (cosine distance): фрагменты дальше этого
# значения отбрасываются — модель не будет «отвечать» по мусору.
# 0.0 = точное совпадение, 0.4–0.5 = хорошо, 0.7+ = обычно не по теме.
SOURCE_MAX_DISTANCE = float(os.getenv("SOURCE_MAX_DISTANCE", "0.55"))

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

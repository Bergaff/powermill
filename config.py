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

# === Какая версия Python подходит ===
# Ниже 3.10 не работает то, что мы используем; выше 3.13 библиотеки ставятся
# дольше (часть ещё не собрана под новые версии), поэтому это предупреждение,
# а не запрет.
PYTHON_MIN = (3, 10)
PYTHON_MAX = (3, 14)

# === Режим работы: eco (днём, за компом) / turbo (ночью, в полную силу) ===
CURRENT_MODE = os.getenv("APP_MODE", "eco")

# === Где лежит код репозитория ===
CODE_DIR = Path(__file__).resolve().parent

# === Корень тяжёлых данных ===
# Порядок такой (первое, что задано, побеждает):
#   1) переменная окружения POWERMILL_DATA_ROOT — так было раньше;
#   2) файл `install.json` рядом с кодом — его пишет install.bat при установке
#      (нужен, чтобы у другого человека всё работало без переменных окружения);
#   3) значение по умолчанию — как в этом проекте, диск E:.
def _settings_file_value(key: str) -> str | None:
    """Читает значение из install.json (пишет установщик). Ничего не ломает."""
    import json

    candidates = []
    custom = os.getenv("POWERMILL_AI_SETTINGS")
    if custom:
        candidates.append(Path(custom))
    candidates.append(CODE_DIR / "install.json")
    for path in candidates:
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


DATA_ROOT = Path(
    os.getenv("POWERMILL_DATA_ROOT")
    or _settings_file_value("data_root")
    or "E:/powermill-ai"
)

DATA_DIR = DATA_ROOT / "data"
PDF_DIR = DATA_DIR / "pdf"
VIDEO_DIR = DATA_DIR / "videos"
MACRO_DIR = DATA_DIR / "macros"
FORUM_DIR = DATA_DIR / "forums"
CHROMA_DIR = DATA_ROOT / "chroma_db"
OUTPUT_DIR = DATA_ROOT / "output"
# Индекс keyword-поиска по справке (SQLite FTS5, встроен в Python)
HELP_SEARCH_DB = Path(os.getenv("POWERMILL_HELP_SEARCH_DB", str(DATA_ROOT / "help_search.db")))

_IS_WINDOWS = os.sys.platform == "win32"
for _d in (PDF_DIR, VIDEO_DIR, MACRO_DIR, FORUM_DIR, CHROMA_DIR, OUTPUT_DIR):
    # На Linux/macOS без POWERMILL_DATA_ROOT не создаём каталог «E:/...»
    # (это путь диска E: на Windows; в Unix он превратился бы в мусорную папку).
    if not _IS_WINDOWS and "POWERMILL_DATA_ROOT" not in os.environ:
        continue
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError as _e:  # например, диска E: нет
        print(f"⚠ Не удалось создать папку {_d}: {_e}")

# === Локальная HTML-справка PowerMill (только чтение, НЕ создаём) ===
# Папки, которые сканирует src.html_parser (существующие — берутся все):
#  1) POWERMILL_HELP_DIR (если задан) либо оффлайн-справка из ProgramData
#  2) всегда, если есть: PML PARREF/PARSUM у установки PowerMill
HELP_DIR = Path(
    os.getenv(
        "POWERMILL_HELP_DIR",
        "C:/ProgramData/Autodesk/PowerMill/2026/Help",
    )
)
# Дополнительные папки справки через ';'
HELP_DIR_EXTRA = [
    Path(p)
    for p in os.getenv("POWERMILL_HELP_DIR_EXTRA", "").split(";")
    if p.strip()
]
HELP_DIR_DEFAULT_EXTRAS = [
    Path("E:/powermill 2026/PowerMill 2026/lib/locale/C"),  # PML reference
]

# === Язык справки ===
# Внутри Help лежат языковые папки: l.rus (русская), l.enu (английская), l.deu ...
# Берём ТОЛЬКО один язык, иначе база забьётся дублями RU+EN.
# Значение "rus" = искать l.rus, "enu" = l.enu, "auto" = первый найденный.
HELP_LANG = os.getenv("POWERMILL_HELP_LANG", "rus").strip().lower()
HELP_LANG_PRIORITY = ["rus", "enu"]  # порядок, если HELP_LANG == "auto"

# 0 = парсить всё (нужно для полной базы). >0 — только N файлов (для быстрой проверки).
HELP_FILE_LIMIT = int(os.getenv("POWERMILL_HELP_FILE_LIMIT", "0"))

# Файлы help-страниц (одна страница = один .htm) и «обёрнутые» JS-файлы,
# в которых MadCap/WebWorks кладёт настоящий HTML.
#   l.rus/files/*.htm        <- оглавление-заглушки (~0.8 КБ)
#   l.rus/wrapped-files/*.js <- реальный текст страницы (до 50 КБ)
HELP_WRAPPED_DIR = "wrapped-files"
HELP_FILES_DIR = "files"

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

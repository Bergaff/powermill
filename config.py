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

    candidates = [settings_path()]
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


def _default_root() -> Path:
    """Папка по умолчанию, если ничего не задано: диск E:, если он есть."""
    if os.sys.platform == "win32" and Path("E:/").exists():
        return Path("E:/powermill-ai")
    if os.sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "PowerMillAI"
    return Path.home() / "powermill-ai"


def _fallback_root() -> Path:
    """Куда переехать, если выбранная папка недоступна (диска нет и т.п.)."""
    if os.sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "PowerMillAI"
    return Path.home() / "powermill-ai"


def settings_path() -> Path:
    """Файл настроек: тот, что задан переменной, иначе install.json рядом с кодом.

    Пишем ровно в тот файл, откуда читаем, — иначе выбор папки не запомнится
    (переменная окружения снова победила бы при следующем запуске).
    """
    custom = os.getenv("POWERMILL_AI_SETTINGS")
    return Path(custom) if custom else CODE_DIR / "install.json"


def requested_data_root() -> tuple[Path, str]:
    """Откуда взялась папка данных и какая она (для объяснения пользователю)."""
    env_value = os.getenv("POWERMILL_DATA_ROOT")
    if env_value:
        return Path(env_value), "переменная POWERMILL_DATA_ROOT"
    settings_value = _settings_file_value("data_root")
    if settings_value:
        return Path(settings_value), "настройка install.json"
    return _default_root(), "значение по умолчанию"


def _try_create(paths: tuple[Path, ...], root: Path) -> str | None:
    """Создаёт папки. Возвращает текст ошибки или None, если всё хорошо."""
    error_text: str | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"сама папка {root}: {error}"
    for folder in paths:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            error_text = f"{folder}: {error}"
    return error_text


# === Запомнить выбранную папку данных ===
def save_data_root(path: Path | str, extra: dict | None = None) -> Path:
    """Пишет install.json рядом с кодом — выбор папки данных пользователем.

    Файл читается при следующем запуске (см. requested_data_root выше), поэтому
    ничего не нужно прописывать в переменных окружения.
    """
    import json
    import time

    data = {
        "data_root": str(Path(path)),
        "chosen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        data.update(extra)
    target = settings_path()
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target

DATA_ROOT, DATA_ROOT_SOURCE = requested_data_root()
DATA_ROOT_NOTE: list[str] = []

_SUBFOLDERS = ("data/pdf", "data/videos", "data/macros", "data/forums",
               "chroma_db", "output")
_IS_WINDOWS = os.sys.platform == "win32"
_MAKE_FOLDERS = _IS_WINDOWS or "POWERMILL_DATA_ROOT" in os.environ

if _MAKE_FOLDERS:
    _error = _try_create(tuple(DATA_ROOT / sub for sub in _SUBFOLDERS), DATA_ROOT)
    if _error:
        # Диска нет, прав нет, путь отключён — НЕ падаем и НЕ сыплем ошибками.
        # Переезжаем в доступную папку и объясняем это одной понятной строкой,
        # а выбор запоминаем в install.json, чтобы спросить больше не пришлось.
        _bad_root = DATA_ROOT
        DATA_ROOT = _fallback_root()
        _error2 = _try_create(tuple(DATA_ROOT / sub for sub in _SUBFOLDERS), DATA_ROOT)
        DATA_ROOT_NOTE.append(
            f"Папку данных «{_bad_root}» использовать не получилось ({_error}).")
        if _error2:
            DATA_ROOT_NOTE.append(
                f"И папку «{DATA_ROOT}» тоже: {_error2}. Данные могут не сохраняться — "
                "выбери папку в окне приложения (кнопка «Папка данных…»).")
        else:
            DATA_ROOT_NOTE.append(
                f"Работаю с папкой «{DATA_ROOT}». Выбрать другую можно в окне "
                "приложения (кнопка «Папка данных…») или запуском install.bat.")
            try:
                save_data_root(DATA_ROOT)
                DATA_ROOT_NOTE.append("Выбор записан в install.json — больше "
                                      "спрашивать не буду.")
            except OSError:
                DATA_ROOT_NOTE.append("Записать выбор в install.json не удалось — "
                                      "спрошу при следующем запуске.")
        for _line in DATA_ROOT_NOTE:
            print(f"⚠ {_line}")

DATA_DIR = DATA_ROOT / "data"
PDF_DIR = DATA_DIR / "pdf"
VIDEO_DIR = DATA_DIR / "videos"
MACRO_DIR = DATA_DIR / "macros"
FORUM_DIR = DATA_DIR / "forums"
CHROMA_DIR = DATA_ROOT / "chroma_db"
OUTPUT_DIR = DATA_ROOT / "output"
# Индекс keyword-поиска по справке (SQLite FTS5, встроен в Python)
HELP_SEARCH_DB = Path(os.getenv("POWERMILL_HELP_SEARCH_DB", str(DATA_ROOT / "help_search.db")))

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

# PowerMill AI — ассистент по Autodesk PowerMill (локально)

Локальный RAG-ассистент для технологов ЧПУ: отвечает на вопросы по документации,
генерирует PML-макросы, транскрибирует видеоуроки. Работает полностью офлайн
через Ollama + ChromaDB.

## Правило дисков: всё тяжёлое — только E:

| Что | Где хранится | Почему |
|---|---|---|
| Код проекта | `E:\powermill-ai` (этот репозиторий) | лёгкий, но рядом с данными |
| PDF, видео, макросы | `E:\powermill-ai\data\...` | десятки ГБ |
| Векторная база ChromaDB | `E:\powermill-ai\chroma_db\` | быстро растёт |
| Модели Ollama (~4 ГБ) | `E:\ollama_models` | не забивать C: |
| Кэш HuggingFace (эмбеддинги) | `E:\hf_cache` | авто скачивается |
| Кэш pip + venv (torch ~2 ГБ) | `E:\pip_cache`, `E:\powermill-ai\venv` | авто скачивается |

Системный SSD (C:) остаётся свободным. Все пути задаются переменными окружения
(см. `config.py`, `scripts/set_heavy_paths.bat`).

## Установка (один раз)

```bat
:: 1. Клонируй репозиторий на диск E (ВАЖНО: не E:\powermill —
::    это папка установки Autodesk, её трогать нельзя!):
E:
cd \
git clone -b arena/01a0c92c-powermill https://github.com/Bergaff/powermill.git powermill-ai
cd powermill-ai

:: 2. Автоустановка: venv, зависимости, папки на E:, переменные окружения
setup.bat

:: 3. Скачай модели Ollama в E:\ollama_models (~4 ГБ)
start_download_models.bat

:: 4. Положи 22 PDF в:  E:\powermill-ai\data\pdf\
::    (видео — по желанию в E:\powermill-ai\data\videos\)
```

> Если клонируешь не на E:\ — `setup.bat` всё равно создаст все тяжёлые папки
> на диске E. Репозиторий желательно держать именно на `E:\powermill-ai`.

## Ежедневный запуск

| Файл | Что делает |
|---|---|
| `start_night_indexing.bat` | Ночью: парсит PDF → транскрибирует видео → строит ChromaDB (режим TURBO) |
| `start_work_chat.bat` | Днём: консольный чат (режим ECO — не грузит систему) |
| `start_download_models.bat` | Качает модели Ollama на E: |

### Команды чата

```
Как сделать чистовую обработку по кривой в 5 осях?   <- обычный вопрос
/macro создать границы по всем отверстиям модели      <- генерация PML-макроса
/exit                                                  <- выход
```

### Telegram-бот (опционально)

```bat
copy .env.example .env
:: впиши токен в .env
python -m src.bot
```

## Структура

```
powermill-ai/                  <- E:\powermill-ai (код в Git)
                                 НЕ путать с E:\powermill — это Autodesk!
├── config.py                  <- все пути и режимы (ECO/TURBO)
├── setup.bat                  <- установка всего на E:
├── start_work_chat.bat        <- дневной чат (ECO)
├── start_night_indexing.bat   <- ночная индексация (TURBO)
├── start_download_models.bat  <- модели Ollama → E:\ollama_models
├── scripts/set_heavy_paths.bat<- перенос переменных окружения на E: навсегда
├── src/
│   ├── pdf_parser.py          <- 22 PDF → текст
│   ├── video_parser.py        <- видео → текст (Whisper)
│   ├── chunker.py             <- текст → чанки
│   ├── vectorstore.py         <- чанки → ChromaDB (E:\powermill-ai\chroma_db)
│   ├── rag.py                 <- чат: поиск + Ollama
│   ├── bot.py                 <- Telegram-бот (aiogram)
│   └── hardware.py            <- приоритеты CPU: ECO днём / TURBO ночью
├── data/pdf/                  <- сюда класть PDF      (E:\powermill-ai\data\pdf)
├── data/videos/               <- сюда класть видео    (E:\powermill-ai\data\videos)
├── data/macros/               <- сюда класть *.mac    (E:\powermill-ai\data\macros)
├── chroma_db/                 <- создаётся на E:\powermill-ai\chroma_db
└── output/                    <- промежуточные файлы  (E:\powermill-ai\output)
```

## Режимы работы

| | ECO (день, `start_work_chat.bat`) | TURBO (ночь, `start_night_indexing.bat`) |
|---|---|---|
| Приоритет CPU | ниже среднего | обычный |
| Потоки | 4 | 10 |
| VRAM Ollama | `keep_alive=0s` — сразу освобождается | `30m` — держится в памяти |
| Назначение | работа в PowerMill параллельно | полная индексация базы |

## Железо (ориентир)

- Windows 10/11, i5, 16 ГБ RAM, RTX 3060 4 ГБ VRAM
- Модели: `qwen2.5:3b` (чат) + `qwen2.5-coder:3b` (PML) — влезают в 4 ГБ
- Эмбеддинги: `paraphrase-multilingual-MiniLM-L12-v2` (мультиязычные RU/EN, ~500 МБ, CPU)

## Источники знаний

| Источник | Команда | Что даёт |
|---|---|---|
| PDF из `data\pdf` | `start_night_indexing.bat` | Robot Setup и пр. |
| **Оффлайн-справка** `C:\ProgramData\Autodesk\PowerMill\2026\Help` | шаг 2 того же батника | User Guide, стратегии, резцы (обычно `l.rus` / `l.enu`) |
| PML PARREF установки | параллельно с оффлайн-справкой | Справочник объектов/команд PML |
| Видео из `data\videos` | шаг 3 | Транскрипты уроков |

Онлайн-скраб help.autodesk.com **удалён** (SPA + гео-блок): используй оффлайн-установщик справки (уже стоит у тебя).

## Требования

- [Python 3.10+](https://www.python.org/downloads/) (Add to PATH)
- [Ollama](https://ollama.com/download/windows)
- [Git](https://git-scm.com/download/win)
- ffmpeg (для видео; `winget install ffmpeg`)

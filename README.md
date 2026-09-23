# PowerMill AI — ассистент по Autodesk PowerMill (локально)

RAG-ассистент для технологов ЧПУ: отвечает по **оффлайн-справке PowerMill**,
генерирует PML-макросы, считает режимы резания, разбирает ошибки.
Работает полностью офлайн: Ollama + ChromaDB + SQLite FTS5.

Это **Уровень 1** из плана: «GitHub Copilot для PowerMill» — подсказывает,
генерирует куски кода, объясняет ошибки.

## Где лежит документация (главное открытие)

Справка Autodesk PowerMill собрана генератором «wrapped HTML», и в папке
`files\` **нет текста** — только заглушки:

```
C:\ProgramData\Autodesk\PowerMill\2026\Help\l.rus\
├── files\           1350 × *.htm   по ~850 БАЙТ — ПУСТЫШКИ (только скрипты!)
├── wrapped-files\   1350 × *.htm.js  0.5–55 КБ — ЗДЕСЬ НАСТОЯЩИЙ ТЕКСТ страниц
├── contexthelp\     1255 × *.htm   короткие подсказки-термины
└── scripts\
    ├── toc-treedata.js     дерево оглавления со всеми заголовками
    └── search-entries*.js  поисковый индекс Autodesk (позиции слов)
```

Именно поэтому «парсинг HTML» по `files\*.htm` давал **0 страниц**: 850 байт —
это `document.write(...)`, а сам текст лежит в `wrapped-files\<имя>.htm.js`
внутри JS-строки (с экранированием `\"`, `\u0413`, склейками `"a" + "b"`).

Что делает проект (см. `src/help_extract.py` и `src/html_parser.py`):

1. находит языковую папку (`l.rus`, `l.enu`, …) — без дублей RU+EN;
2. берёт текст из `files\*.htm`, а если там заглушка — разворачивает
   `wrapped-files\*.js` (все варианты обёрток: `document.write`, `append`,
   `innerHTML`, конкатенация, `\uXXXX`-escape);
3. подтягивает **заголовок и иерархию** из `scripts\toc-treedata.js`
   (например, `Начало работы > Введение > Установка домашней папки`);
4. чистит навигацию/«было полезно?», сохраняет структуру: `## Заголовки`,
   `- списки`, `| таблицы |`, `[рисунок: …]`;
5. пишет `output\help_pages.jsonl`, `output\help_toc.txt`, `output\help_report.txt`.

## Команды (Уровень 1 — реализовано)

| Команда | Пример | Что делает |
|---|---|---|
| `/ask` или просто вопрос | «Как сделать чистовую обработку по кривой в 5 осях?» | ответ по справке + список источников |
| `/macro` | «создать границы по всем отверстиям модели» | PML-код, автоматически сохраняется в `output\macros\*.mac` |
| `/cutting` | «Сталь 40Х, фреза D16 Sandvik, черновая» | S, F, ap, ae, мощность, стратегия — **детерминированный расчёт**, без выдумок LLM |
| `/error` | «Toolpath calculation failed — undercut» | причина + варианты решения |
| `/compare` | «Чем Model Area Clearance отличается от Offset Area?» | таблица сравнения |
| `/sources` | «/sources границы по отверстиям» | отладка: что нашлось в базе и с какой близостью |
| `/stats` | | состав базы знаний (вектора + FTS) |

Telegram-бот (`python -m src.bot`) поддерживает те же команды.

## Как работает поиск

Гибрид, слияние по Reciprocal Rank Fusion (`src/retrieval.py`):

| Канал | Что ловит | Где |
|---|---|---|
| Вектора (ChromaDB + MiniLM-multilingual) | смысл, перефразировку | `src/vectorstore.py` |
| Ключевые слова (SQLite **FTS5**, встроен в Python) | точные термины: `Thickness`, `HOLDER_CLEARANCE`, «D16», русскую морфологию через усечение окончаний | `src/help_search.py` |

Строгие FTS-совпадения считаются релевантными всегда, векторные — только при
`distance ≤ SOURCE_MAX_DISTANCE`. Если векторная база пуста, ассистент всё
равно отвечает по FTS (и наоборот). Смена модели эмбеддингов требует полной
пересборки: `python -m src.vectorstore`.

## Правило дисков: всё тяжёлое — только E:

| Что | Где хранится |
|---|---|
| Код проекта | `E:\powermill-ai` (этот репозиторий) |
| PDF, видео, макросы | `E:\powermill-ai\data\...` |
| ChromaDB + `help_search.db` | `E:\powermill-ai\` |
| Промежуточные файлы, отчёты, макросы | `E:\powermill-ai\output\` |
| Модели Ollama (~4 ГБ) | `E:\ollama_models` |
| Кэш HuggingFace / pip, venv | `E:\hf_cache`, `E:\pip_cache`, `E:\powermill-ai\venv` |

> `E:\powermill` — это папка установки Autodesk, её трогать нельзя.
> Репозиторий — `E:\powermill-ai` (через дефис).

## Установка (один раз)

```bat
E:
cd \
git clone -b arena/01a0ce77-powermill https://github.com/Bergaff/powermill.git powermill-ai
cd powermill-ai
setup.bat                  :: venv + зависимости + папки на E:
start_download_models.bat  :: модели Ollama (~4-5 ГБ)
```

## Первый запуск: научить базу читать справку

```bat
:: 1. Диагностика: что лежит в Help (образцы файлов -> output\help_samples)
scripts\dump_help_samples.bat

:: 2. Быстрая проверка парсера на 30 страницах + отчёт
start_parse_help.bat 30

:: 3. Полный разбор справки (~2600 страниц) и построение FTS-индекса
start_parse_help.bat

:: 4. Векторная база (эмбеддинги, ночью в режиме TURBO)
start_reindex_help.bat

:: 5. Чат
start_work_chat.bat
```

Проверить поиск без чата и без ИИ (мгновенно):

```bat
python -m src.help_search "чистовая обработка по кривой"
python -m src.help_search "Swarf"
python -m src.cutting "Сталь 40Х, фреза D16, черновая"
```

## Ежедневный запуск

| Файл | Что делает |
|---|---|
| `start_work_chat.bat` | днём: консольный чат (ECO — не грузит систему) |
| `start_parse_help.bat [N]` | разбор справки + FTS-индекс; `[N]` — пробный прогон |
| `start_reindex_help.bat` | пересборка векторной базы после обновления справки |
| `start_night_indexing.bat` | ночью: PDF → видео → справка → ChromaDB (TURBO) |
| `start_download_models.bat` | модели Ollama на диск E |
| `scripts\dump_help_samples.bat` | диагностика справки (когда «мало текста») |
| `scripts\fix_ollama.bat` | Ollama не отвечает на 11434 |

## Режимы

| | ECO (день) | TURBO (ночь) |
|---|---|---|
| Приоритет CPU | ниже среднего | обычный |
| Потоки | 4 | 10 |
| VRAM Ollama | `keep_alive=0s` | `30m` |
| Чанк / TOP_K | 500 / 3 | 700 / 5 |

## Железо (ориентир)

Windows 10/11, i5, 16 ГБ RAM, RTX 3060.
Модели: `qwen2.5:3b` (чат) + `qwen2.5-coder:3b` (PML) — влезают в 4 ГБ VRAM;
при 12 ГБ — 7B (`start_download_models.bat` переключит).

## Тесты

```bat
venv\Scripts\activate
pip install pytest
python -m pytest tests -q
```

79 тестов: разбор обёрток справки, оглавление, парсер, FTS-поиск, гибридный
ретривер, чанкер, режимы резания, команды ассистента. Тесты работают на
синтетической справке `tests\fixture_help` (заглушки + wrapped-files + оглавление),
поэтому не требуют ни PowerMill, ни Ollama, ни chromadb.

## Структура

```
powermill-ai/
├── config.py                     все пути, языки, режимы ECO/TURBO
├── start_work_chat.bat           дневной чат
├── start_parse_help.bat [N]      разбор справки + FTS-индекс
├── start_reindex_help.bat        пересборка векторной базы
├── start_night_indexing.bat      ночная полная индексация
├── start_download_models.bat     модели Ollama -> E:\ollama_models
├── scripts/
│   ├── dump_help_samples.py/.bat диагностика справки
│   ├── find_help.bat             поиск папки справки
│   ├── set_heavy_paths.bat       перенос тяжёлого на E: навсегда
│   └── fix_ollama.bat            лечение Ollama
├── src/
│   ├── help_extract.py           wrapped-files -> чистый текст
│   ├── toc_parser.py             оглавление -> заголовки и разделы
│   ├── html_parser.py            вся справка -> output\help_pages.jsonl
│   ├── help_search.py            FTS5 keyword-поиск
│   ├── retrieval.py              гибридный поиск (RRF)
│   ├── chunker.py                текст -> чанки с шапкой раздела
│   ├── vectorstore.py            ChromaDB (диск E)
│   ├── cutting.py                режимы резания (формулы, без LLM)
│   ├── rag.py                    команды + Ollama + консольный чат
│   ├── bot.py                    Telegram-бот (aiogram 3)
│   ├── pdf_parser.py             PDF -> текст
│   ├── video_parser.py           видео -> текст (Whisper)
│   └── hardware.py               приоритеты CPU для ECO/TURBO
├── tests/                        79 тестов на синтетической справке
└── output/                       отчёты, JSONL страниц, сгенерированные .mac
```

## Что дальше (Уровень 2)

- плагин в интерфейсе PowerMill (PML-макрос-мост к локальному API ассистента);
- анализ модели STEP/STL: распознавание отверстий/карманов и подбор стратегий;
- автозаполнение параметров траектории (S, F, ap, ae, допуски) через `/cutting`;
- проверка траектории: «врезание 90° на участке 3 — поставь ramp»;
- генерация G-кода через постпроцессор и API PowerMill.

## Требования

- Python 3.10+, Ollama, Git, ffmpeg (для видео)
- ChromaDB, sentence-transformers, faster-whisper — ставятся `setup.bat`
- SQLite FTS5 — встроен в Python, ничего ставить не нужно

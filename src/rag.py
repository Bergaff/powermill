"""
RAG-ассистент по PowerMill: гибридный поиск (вектора + FTS5) + Ollama.

Команды (CLI и Telegram используют один и тот же класс PowerMillAI):

    <вопрос>              /ask   — ответ по документации, с источниками
    /macro <задача>              — генерация PML-макроса (сохраняется в .mac файл)
    /cutting <материал> <фреза>  — режимы резания (детерминированный расчёт, без LLM)
    /error <текст ошибки>        — разбор ошибки: причина + варианты решения
    /compare A и B               — сравнение двух стратегий/инструментов (таблица)
    /sources <вопрос>            — что нашлось в базе (отладка поиска)
    /stats                       — что в базе знаний
    /exit                        — выход

Запуск: python -m src.rag            (интерактивный чат)
        python -m src.rag --once "Как сделать чистовую по кривой?"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

from config import (
    CURRENT_MODE,
    LLM_CODE_MODEL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    SOURCE_MAX_DISTANCE,
    TOP_K,
)
from src import cutting, llm, pml_vocab, project_context
from src.hardware import set_process_priority

os.environ.setdefault("OLLAMA_HOST", OLLAMA_BASE_URL)

try:
    import ollama
except ImportError:  # pragma: no cover — чат без LLM тоже должен работать
    ollama = None


SYSTEM_PROMPT_CHAT = """Ты — инженер-технолог ЧПУ, эксперт по Autodesk PowerMill.

Жёсткие правила:
1. Отвечай ТОЛЬКО по контексту из базы знаний ниже.
2. Если в контексте нет ответа — прямо напиши: "В документации по этому вопросу
   ничего не нашёл" и предложи 2–3 слова/термина, по которым стоит искать.
   НИЧЕГО не выдумывай.
3. Ссылайся на номера фрагментов: [1], [2] — читатель должен видеть, откуда факт.
4. Отвечай на русском, по шагам, коротко и по делу. Без общих фраз.
5. Если в контексте есть названия кнопок/полей на английском — приводи их
   как в интерфейсе PowerMill (например, «Подача (Feed rate)»).

Контекст из базы знаний PowerMill:
{context}
"""

SYSTEM_PROMPT_MACRO = """Ты — эксперт по макроязыку PML (PowerMill Macro Language).

Задача: написать РАБОЧИЙ макрос PML по описанию технолога.

Синтаксис PML (соблюдай строго, это НЕ Python и НЕ C):
- Макрос начинается с комментариев: // описание
- Переменные: $var = "text"   $n = 12   $n = $n + 1
- Условия:   IF $var == "x" { ... } ELSE { ... } ENDIF
- Циклы:     FOREACH $e IN $entities { ... }   WHILE $n < 10 { ... } ENDWHILE
- Объекты:   ENTITY $e   FOREACH $tp IN FOLDER("Toolpath") { ... }
- Команды PowerMill — ТОЛЬКО ЗАГЛАВНЫМИ буквами: CREATE BOUNDARY ;
  ACTIVATE TOOLPATH $tp.name   EDIT TOOLPATH $tp.name ; REORDER
- PML различает регистр: «Create Boundary» и «Create» — ошибка, нужно
  CREATE BOUNDARY.
- Комментарии: // текст

ЖЁСТКИЕ ПРАВИЛА (важнее красоты кода):
1. Типы объектов и параметры бери ТОЛЬКО из блока «ПРОВЕРЕННЫЕ ИМЕНА» ниже.
2. Если для задачи нужна команда или объект, которых нет в проверенных именах —
   НЕ ВЫДУМЫВАЙ. Вместо строки оставь комментарий:
   // НЕ НАЙДЕНО В ДОКУМЕНТАЦИИ: <что нужно сделать>
   и продолжай с того места, где уверен.
3. Не добавляй пояснения после кода, кроме 1–2 строк заметок // NOTE: ...
4. Если задача совсем не покрыта документацией — напиши это первой строкой
   комментария и дай только каркас с комментариями вместо команд.

Фрагменты документации PowerMill:
{context}

ПРОВЕРЕННЫЕ ИМЕНА (из разобранной документации PowerMill):
{vocabulary}
"""

SYSTEM_PROMPT_ERROR = """Ты — наладчик/технолог, разбираешь ошибки PowerMill.

По тексту ошибки и найденным фрагментам документации выдай СТРОГО такую структуру:

**Причина** — 1–3 предложения, что именно не так.
**Что проверить и как исправить** — нумерованный список конкретных действий
(пункты интерфейса, параметры, значения).
**Если не помогло** — 1–2 альтернативные причины.

Не выдумывай пункты меню, которых нет в контексте. Если контекст пустой —
скажи честно и предложи поискать по другому слову.

Найденный контекст:
{context}
"""

SYSTEM_PROMPT_COMPARE = """Ты — инженер-технолог PowerMill. Сравни два объекта из вопроса.

Формат ответа — таблица в Markdown:

| Критерий | <Объект A> | <Объект B> |
|---|---|---|
| Что это | | |
| Назначение | | |
| Когда применять | | |
| Ключевые параметры (имена из документации) | | |
| Ограничения и риски | | |
| Близкая стратегия | | |

ТРЕБОВАНИЯ:
1. Объект A описывается ТОЛЬКО по фрагментам блока «=== A ===», объект B —
   ТОЛЬКО по блокам «=== B ===». Не смешивай их.
2. В каждой ячейке указывай номер источника, например: «обработка стенок [2]».
3. «Ключевые параметры» — реальные имена из документации (Thickness, LeadAngle,
   SwarfBasePosition и т. п.). Если имён нет — напиши «в документации не найдено».
4. Ничего не придумывай. Лучше пустая ячейка, чем выдумка.
5. После таблицы 2–4 строки «Практический вывод»: что выбрать в каких случаях.

Контекст:
{context}
"""

# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------
def _render(prompt: str, context: str, **extra: str) -> str:
    """Подставляет контекст (и доп. блоки) в промпт.

    Через str.replace, а не str.format: в промпте про PML есть фигурные скобки
    синтаксиса (`IF $x == "y" { ... }`), и format() на них падает.
    """
    out = prompt.replace("{context}", context)
    for key, value in extra.items():
        out = out.replace("{" + key + "}", value)
    return out


def _format_hits(hits: list[dict], numbered: bool = True, start: int = 1) -> str:
    """Склеивает фрагменты в контекст для промпта (с нумерацией для ссылок)."""
    if not hits:
        return "(пусто — релевантных фрагментов не найдено)"
    parts: list[str] = []
    for i, h in enumerate(hits, start):
        head = h.get("breadcrumb") or h.get("title") or h.get("source", "?")
        mark = f"[{i}] " if numbered else ""
        found = h.get("found_by", "")
        dist = h.get("distance")
        meta = f"источник: {h.get('source', '?')}"
        if dist is not None:
            meta += f", dist={dist:.2f}"
        if found:
            meta += f", найдено: {found}"
        parts.append(f"{mark}({meta})\n{head}\n{h['text']}")
    return "\n---\n".join(parts)


def _format_sources(hits: list[dict]) -> str:
    if not hits:
        return "📚 Источники: не найдено (ни один фрагмент не прошёл фильтр)"
    lines = ["📚 Источники:"]
    for i, h in enumerate(hits, 1):
        crumb = h.get("breadcrumb") or h.get("title") or "?"
        dist = h.get("distance")
        extra = f"  (dist={dist:.2f}, {h.get('found_by', '')})" if dist is not None else \
                f"  ({h.get('found_by', '')})"
        lines.append(f"  [{i}] {crumb}{extra}")
        lines.append(f"      {h.get('source', '?')}")
    return "\n".join(lines)


def split_compare(query: str) -> tuple[str, str]:
    """«Чем A отличается от B» -> (A, B)."""
    q = re.sub(r"^(чем|что лучше|сравни|сравнить|compare)\s*", "", query.strip(),
               flags=re.I)
    q = re.sub(r"[?.!]+$", "", q)
    for sep in (" отличается от ", " vs ", " versus ", " или ", " и ", " / "):
        if sep in q:
            left, right = q.split(sep, 1)
            left = re.sub(r"^(чем|сравни)\s*", "", left, flags=re.I).strip()
            return left.strip(" ,:;"), right.strip(" ,:;")
    return q, ""


class PowerMillAI:
    """Всё, что нужно чату: поиск, генерация, режимы резания."""

    def __init__(self, store=None, fts=None, load_fts: bool = True,
                 verbose: bool = True):
        """store/fts можно подставить свои (используется в тестах)."""
        set_process_priority(CURRENT_MODE)

        if store is None:
            from src.vectorstore import PowerMillVectorStore

            store = PowerMillVectorStore()
        self.store = store

        self.fts = fts
        if self.fts is None and load_fts:
            try:
                from src.help_search import HelpSearch

                self.fts = HelpSearch()
                if self.fts.pages_file.exists():
                    self.fts.ensure_index(verbose=verbose)
                    if verbose:
                        st = self.fts.stats()
                        print(f"📚 Справка: {st['pages']} страниц в keyword-индексе "
                              f"({st['size_mb']} МБ)")
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print(f"⚠ Keyword-индекс недоступен: {e}")
                self.fts = None

        from src.retrieval import HybridRetriever

        self.retriever = HybridRetriever(self.store, self.fts, verbose=verbose)

    # ---------------- LLM ----------------
    def _generate(self, model: str, prompt: str, temperature: float = 0.2,
                  num_predict: int = 2048, num_ctx: int = 4096) -> str:
        """Один ответ модели: облачный API, если настроен, иначе локальная Ollama.

        Модель выбирается не по имени, а по режиму (src/llm.py):
        * `backend=api` — идём в OpenAI-совместимый сервис с ключом;
        * `backend=local` — как раньше, в Ollama.
        """
        settings = llm.load_settings()
        if settings["backend"] == "api":
            api_model = (settings.get("code_model") if model == LLM_CODE_MODEL
                         else settings.get("model")) or settings.get("model", "")
            return llm.chat(prompt, model=api_model, settings=settings,
                            temperature=temperature, max_tokens=num_predict)

        if ollama is None:
            return "❌ Модуль ollama не установлен: pip install ollama"
        try:
            response = ollama.generate(
                model=model,
                prompt=prompt,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options={
                    "temperature": temperature,
                    "num_predict": num_predict,
                    "num_ctx": num_ctx,
                },
            )
            return response["response"]
        except Exception as e:  # noqa: BLE001
            return (
                f"❌ Ошибка Ollama: {e}\n"
                f"Проверь, что Ollama запущена и модель {model} загружена "
                f"(ollama pull {model})."
            )

    def _retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        return self.retriever.search(query, top_k=top_k or TOP_K)

    # ---------------- команды ----------------
    def ask(self, query: str) -> str:
        """Обычный вопрос по документации."""
        hits = self._retrieve(query)
        context = _format_hits(hits)
        project = project_context.to_prompt_block()
        if project:
            context = project + "\n\n" + context
        prompt = _render(SYSTEM_PROMPT_CHAT, context)
        answer = self._generate(LLM_MODEL, f"{prompt}\n\nВопрос технолога: {query}\n\nОтвет эксперта:")
        return f"{answer}\n\n{_format_sources(hits)}"

    def macro(self, task: str, save: bool = True) -> str:
        """Генерация PML-макроса: с проверенными именами и проверкой результата.

        Модель не должна выдумывать команды, которых нет в PML. Поэтому:
        1) в промпт кладём словарь настоящих типов объектов и параметров,
           собранный из разобранной документации (src/pml_vocab.py);
        2) готовый макрос проверяем по этому же словарю и показываем технологу
           конкретные подозрительные строки.
        """
        vocab = pml_vocab.load_vocabulary()
        project = project_context.load()
        # ищем и по задаче, и по именам объектов проекта — чтобы в контекст
        # попали статьи именно про эти объекты
        query = f"{task} PML макрос PowerMill"
        if project:
            query += " " + " ".join(
                (project.get(section) or [""])[0]
                for section in ("toolpaths", "boundaries", "tools"))
        hits = self._retrieve(query, top_k=max(TOP_K, 6))

        entities = pml_vocab.relevant_entities(task, vocab, limit=25)
        params = pml_vocab.relevant_parameters(task, hits, vocab, limit=40)
        vocabulary = (
            "Типы объектов (пишутся после CREATE/DELETE/EDIT/ACTIVATE):\n  "
            + ", ".join(entities)
            + "\n\nИмена параметров (встречаются в этой задаче):\n  "
            + (", ".join(params) if params else "(в документации не найдено)")
        )
        if not vocab.get("entities"):
            vocabulary += ("\n\n(!) Словарь PML пуст — справка ещё не разобрана. "
                           "Разбери справку (пункт 4 меню), и макросы станут точнее.")

        project_block = project_context.to_prompt_block(project)

        prompt = _render(SYSTEM_PROMPT_MACRO, _format_hits(hits),
                         vocabulary=vocabulary + ("\n\n" + project_block
                                                  if project_block else ""))
        code = self._generate(LLM_CODE_MODEL,
                              f"{prompt}\n\nЗадача: {task}\n\nКод PML:",
                              temperature=0.2)

        report = pml_vocab.validate(code, vocab)
        out = f"⚙️ PML-макрос по задаче: {task}\n\n{code}"
        out += f"\n\n{pml_vocab.format_check(report)}"
        if save:
            path = save_macro(code, task, check=report)
            if path:
                out += f"\n\n💾 Сохранён файл: {path}"
        out += f"\n\n{_format_sources(hits)}"
        return out

    def cutting_answer(self, text: str) -> str:
        """Режимы резания — детерминированный расчёт (без LLM)."""
        report, data = cutting.answer(text)
        return report

    def error(self, text: str) -> str:
        """Разбор ошибки PowerMill."""
        hits = self._retrieve(f"ошибка {text}", top_k=max(TOP_K, 5))
        if not hits:
            hits = self._retrieve(text, top_k=max(TOP_K, 5))
        prompt = _render(SYSTEM_PROMPT_ERROR, _format_hits(hits))
        answer = self._generate(LLM_MODEL, f"{prompt}\n\nТекст ошибки: {text}\n\nРазбор:")
        return f"{answer}\n\n{_format_sources(hits)}"

    def compare(self, query: str) -> str:
        """Сравнение двух стратегий/инструментов."""
        left, right = split_compare(query)
        if not right:
            return ("⚠️ Не понял, что сравнивать. Пример: "
                    "/compare Model Area Clearance и Offset Area Clearance")
        hits_left = self._retrieve(left, top_k=max(2, TOP_K - 1))
        hits_right = self._retrieve(right, top_k=max(2, TOP_K - 1))
        seen: set[str] = set()
        hits: list[dict] = []
        for h in hits_left + hits_right:
            key = f"{h.get('source')}::{h['text'][:60]}"
            if key in seen:
                continue
            seen.add(key)
            hits.append(h)

        # Контекст даём ДВУМЯ блоками: модель не должна смешивать объекты A и B.
        context = (
            f"=== A: {left} ===\n"
            + _format_hits(hits_left)
            + f"\n\n=== B: {right} ===\n"
            + _format_hits(hits_right, start=len(hits_left) + 1)
        )
        prompt = _render(SYSTEM_PROMPT_COMPARE, context)
        answer = self._generate(
            LLM_MODEL,
            f"{prompt}\n\nСравни «{left}» и «{right}».\n\nОтвет:",
        )

        out = answer
        # Если документация нашлась, а модель всё равно пишет «нет данных» —
        # показываем технологу сами фрагменты, чтобы он решил сам.
        low = answer.lower()
        empty_cells = low.count("не найдено") + low.count("нет данных") + low.count("n/a")
        if empty_cells >= 3 and (hits_left or hits_right):
            out += "\n\n" + _fallback_facts(left, hits_left, right, hits_right)
        return f"{out}\n\n{_format_sources(hits)}"

    def sources(self, query: str, top_k: int = 6) -> str:
        """Отладка поиска: сырые попадания."""
        hits = self.retriever.explain(query, top_k=top_k)
        if not hits:
            return ("(нет результатов поиска — база пуста или повреждена;\n"
                    " запусти start_reindex_help.bat)")
        lines = [f"Найдено для: {query!r}",
                 f"Порог релевантности: {SOURCE_MAX_DISTANCE} (меньше = точнее), TOP_K={TOP_K}",
                 ""]
        for i, h in enumerate(hits, 1):
            dist = h.get("distance")
            passed = "OK  " if dist is not None and dist <= SOURCE_MAX_DISTANCE else \
                     ("FTS " if h.get("found_by") == "fts" else "SKIP")
            crumb = (h.get("breadcrumb") or h.get("title") or "?")[:80]
            lines.append(f"  {i}. [{passed}] {h.get('found_by', '?'):<12} "
                         f"dist={dist if dist is None else round(dist, 3)}")
            lines.append(f"     {crumb}")
            lines.append(f"     {h['text'][:180].replace(chr(10), ' ')}...")
            lines.append("")
        return "\n".join(lines)

    def project(self) -> str:
        """Что известно о проекте технолога + проверки по нему."""
        context = project_context.load()
        if not context:
            return ("Снимок проекта пока не загружен, поэтому макросы пишутся "
                    "с абстрактными именами.\n\n"
                    "Как загрузить (30 секунд):\n"
                    "  1) пункт 23 меню — создаст макрос разведки "
                    "output\\PM_PROBE.mac;\n"
                    "  2) запусти его в PowerMill (вкладка «Макрос» -> Выполнить);\n"
                    "  3) пункт 24 меню — вставь вывод в блокнот, сохрани и закрой.")
        text = project_context.summary(context)
        checks = project_context.format_checks(context)
        if checks:
            text += "\n\n" + checks
        return text

    def pm_status(self) -> str:
        """Живое подключение к PowerMill (шаг 2.1).

        Без моста — объясняем, что сделать (пункт 27). С мостом — сразу делаем
        разведку API и сохраняем отчёт для отправки в чат.
        """
        from src import pm_live, pm_probe

        if not any(pm_live.bridges().values()):
            return (pm_live.status_report(verbose=False)
                    + "\n\nЧто сделать: пункт 27 меню — поставить мост к PowerMill.\n"
                      "После этого /pm покажет структуру API и подключится к проекту.")

        pm_probe.run(verbose=True)
        return (f"Отчёт разведки сохранён: {pm_probe.PROBE_FILE}\n"
                f"Пришли его в чат — по нему будет точное подключение к проекту.")

    def ai_line(self) -> str:
        """Строка «какой ИИ используется» для статуса и отчётов."""
        try:
            return llm.describe_settings()
        except Exception:  # noqa: BLE001
            return "ИИ: не удалось прочитать настройки"

    def stats(self) -> str:
        """Что сейчас в базе знаний."""
        st = self.store.stats()
        lines = [f"🧠 Векторная база: {st['total']} чанков ({st['path']})"]
        for key, cnt in sorted(st["by_type"].items(), key=lambda kv: -kv[1]):
            lines.append(f"    {key:<15} {cnt}")
        if self.fts is not None:
            fst = self.fts.stats()
            lines.append(f"🔎 FTS-индекс: {fst['pages']} страниц, "
                         f"{fst['size_mb']} МБ ({fst['db']})")
        else:
            lines.append("🔎 FTS-индекс: не подключён")
        pages = Path(self.fts.pages_file).parent / "help_pages.jsonl" if self.fts else None
        if pages and pages.exists():
            size = pages.stat().st_size / 1e6
            lines.append(f"📄 help_pages.jsonl: {size:.1f} МБ")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Сохранение макросов
# --------------------------------------------------------------------------
def _fallback_facts(left: str, hits_left: list[dict],
                    right: str, hits_right: list[dict]) -> str:
    """Показывает сырые фрагменты по обеим сторонам, если модель сдалась.

    Иногда документация есть, но модель пишет «нет данных». Тогда технологу
    полезнее увидеть сами выдержки, чем пустую таблицу.
    """
    lines = ["📄 Что нашлось в документации (сырые выдержки):"]

    def side(name: str, hits: list[dict]) -> None:
        lines.append(f"\n  {name}:")
        if not hits:
            lines.append("    — в базе ничего не найдено, попробуй другое слово")
            return
        for hit in hits[:3]:
            crumb = hit.get("breadcrumb") or hit.get("title") or hit.get("source", "?")
            text = re.sub(r"\s+", " ", hit.get("text", "")).strip()
            lines.append(f"    • {crumb}")
            lines.append(f"      {text[:220]}…")
            lines.append(f"      {hit.get('source', '?')}")

    side(left, hits_left)
    side(right, hits_right)
    lines.append("\n  Полный текст: пункт 2 меню (поиск по справке), потом цифра статьи.")
    return "\n".join(lines)


def save_macro(text: str, task: str, check: dict | None = None) -> Path | None:
    """Вытаскивает код из ответа LLM и сохраняет в выходную папку.

    Если передана проверка (src/pml_vocab.validate) — первой строкой файла
    пишем её итог, чтобы технолог видел риск прямо в макросе.
    """
    try:
        from config import OUTPUT_DIR

        folder = OUTPUT_DIR / "macros"
        folder.mkdir(parents=True, exist_ok=True)
        code = extract_code(text)
        if not code.strip():
            return None
        slug = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", "_", task.strip())[:40].strip("_") or "macro"

        header = [f"// Задача: {task}",
                  f"// Создано: PowerMill AI, {time.strftime('%Y-%m-%d %H:%M')}"]
        if check is not None:
            if check.get("ok"):
                header.append("// Проверка по документации: подозрительных строк нет")
            else:
                suspects = (check.get("not_commands", []) + check.get("unknown_types", [])
                            + check.get("case_errors", []) + check.get("bad_arity", []))
                numbers = ", ".join(str(n) for n, _line in suspects[:10])
                header.append("// ВНИМАНИЕ: проверь строки " + numbers
                              + " — они не найдены в документации PowerMill")
                header.append("// Подробности: пункт 2 меню (поиск по справке)")
        header.append("")

        path = folder / f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}.mac"
        path.write_text("\n".join(header) + code, encoding="utf-8")
        return path
    except Exception:  # noqa: BLE001 — сохранение не должно ломать ответ
        return None


def extract_code(text: str) -> str:
    """Достаёт код из ```-блока; если блока нет — возвращает текст как есть."""
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
    if blocks:
        return max(blocks, key=len).strip()
    return text.strip()


# --------------------------------------------------------------------------
# Интерактивный чат
# --------------------------------------------------------------------------
HELP_TEXT = """\
Команды:
  <обычный вопрос>              — ответ по документации (/ask)
  /ask <вопрос>                 — то же самое, явно
  /macro <задача>               — сгенерировать PML-макрос (файл сохраняется)
  /cutting <материал> <фреза>   — режимы резания S/F/ap/ae (расчёт, без ИИ)
  /error <текст ошибки>         — причина ошибки + что исправить
  /compare <A> и <B>            — сравнение двух стратегий (таблица)
  /project                      — проект PowerMill: объекты и проверки (пункты 23-24)
  /pm                           — живое подключение к PowerMill (шаг 2.1)
  /sources <вопрос>             — что нашлось в базе (отладка)
  /stats                        — состав базы знаний
  /exit  (или «назад», «меню»)  — выход в главное меню

Примеры:
  Как сделать чистовую обработку по кривой в 5 осях?
  /macro создать границы по всем отверстиям модели
  /cutting Сталь 40Х, фреза D16 Sandvik, черновая
  /error Toolpath calculation failed - undercut
  /compare Model Area Clearance и Offset Area Clearance
"""


def handle_command(q: str, ai: PowerMillAI) -> bool:
    """Обрабатывает одну строку. Возвращает False, если надо выйти."""
    low = q.lower().strip()

    # «назад» и «меню» возвращают к выбору пункта главного меню
    if low in {"/exit", "exit", "quit", "/q", "/выход", "назад", "/назад",
               "меню", "/меню", "/menu"}:
        return False
    if low in {"/help", "help", "/?", "/помощь"}:
        print(HELP_TEXT)
        return True
    if low.startswith("/stats"):
        print("\n" + ai.stats())
        return True
    if low.startswith("/sources"):
        rest = q[len("/sources"):].strip()
        print("\n" + (ai.sources(rest) if rest
                      else "⚠️ Использование: /sources как сделать границу"))
        return True
    if low.startswith("/project"):
        print("\n" + ai.project())
        return True
    if low.startswith("/pm"):
        print("\n🤖 Пробую подключиться к PowerMill...")
        print(ai.pm_status())
        return True
    if low.startswith("/cutting"):
        rest = q[len("/cutting"):].strip()
        print("\n" + (ai.cutting_answer(rest) if rest else HELP_TEXT))
        return True

    if low.startswith("/macro"):
        task = q[len("/macro"):].strip()
        if not task:
            print("⚠️ Укажи задачу: /macro создать границы по всем отверстиям")
            return True
        print("\n🤖 Генерирую PML-макрос...")
        print(f"\n💡 Ответ:\n{ai.macro(task)}")
        return True

    if low.startswith("/error"):
        rest = q[len("/error"):].strip()
        if not rest:
            print("⚠️ Укажи текст ошибки: /error Toolpath calculation failed")
            return True
        print("\n🤖 Разбираю ошибку...")
        print(f"\n💡 Ответ:\n{ai.error(rest)}")
        return True

    if low.startswith("/compare"):
        rest = q[len("/compare"):].strip()
        print("\n🤖 Сравниваю...")
        print(f"\n💡 Ответ:\n{ai.compare(rest)}")
        return True

    if low.startswith("/ask"):
        q = q[len("/ask"):].strip()
        if not q:
            print("⚠️ Использование: /ask как задать врезание по спирали")
            return True

    print("\n🤖 ИИ думает...")
    print(f"\n💡 Ответ:\n{ai.ask(q)}")
    return True


def run_chat() -> None:
    ai = PowerMillAI()
    print("\n" + "=" * 60)
    print(" 🤖 PowerMill AI Assistant готов к работе!")
    try:
        from src import llm as _llm

        print(f" 🧠 {_llm.describe_settings()}")
        print("    (сменить ИИ: пункт 22 меню — локальный или API)")
    except Exception:  # noqa: BLE001
        pass
    print("=" * 60)
    print(HELP_TEXT)

    while True:
        try:
            q = input("\n👨‍💻 Технолог: ").strip()
            if not q:
                continue
            if not handle_command(q, ai):
                print("👋 Возвращаюсь в меню (start_menu.bat)")
                break
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Возвращаюсь в меню (start_menu.bat)")
            break


def main() -> None:
    ap = argparse.ArgumentParser(description="PowerMill AI — чат по документации")
    ap.add_argument("--once", metavar="ВОПРОС",
                    help="ответить на один вопрос и выйти (для батников/тестов)")
    ap.add_argument("--command", default="", help="команда для --once: ask/macro/"
                                                  "cutting/error/compare/sources/stats")
    ap.add_argument("--no-llm", action="store_true",
                    help="без Ollama: только поиск по справке (проверка базы знаний)")
    args = ap.parse_args()

    if args.command == "cutting" or (args.once and args.once.lower().startswith("/cutting")):
        text = args.once[len("/cutting"):].strip() if args.once.lower().startswith("/cutting") else args.once
        print(cutting.answer(text or "")[0])
        return

    # Без ИИ: только поиск по справке (ключевые слова) — работает всегда
    if args.no_llm and not args.once:
        from src.help_search import interactive

        interactive()
        return

    if args.once:
        if args.no_llm or args.command in {"sources", "stats"}:
            from src.help_search import HelpSearch, print_hits

            hs = HelpSearch()
            hs.ensure_index()
            if args.command == "stats":
                print(hs.stats())
                return
            hits = hs.search(args.once, top_k=8)
            if not hits:
                print("Ничего не найдено.")
                return
            print_hits(hits)
            return
        ai = PowerMillAI(verbose=False)
        command_line = (f"/{args.command} {args.once}".strip()
                        if args.command else args.once)
        handle_command(command_line, ai)
        return

    run_chat()


if __name__ == "__main__":
    sys.exit(main())

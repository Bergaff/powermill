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
from src import cutting
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
- Условия:   IF $var == "x" { ... } ELSE { ... }
- Циклы:     FOREACH $e IN $entities { ... }   WHILE $n < 10 { ... }
- Объекты:   ENTITY $e   FOREACH $p IN FOLDER("Model") { ... }
- Команды PowerMill по имени: Create Boundary; Activate Toolpath "x";  (строки-команды)
- Комментарии: // текст
- Ошибки в макросе PowerMill: "macros are case sensitive" — соблюдай регистр команд.

Требования к ответу:
1. Только код PML + короткие комментарии на русском ВНУТРИ кода.
2. Если опирался не на документацию, а на общее знание — первой строкой:
   // ВНИМАНИЕ: сгенерировано без опоры на документацию, проверь синтаксис
3. Никаких пояснений после кода, кроме 1–2 строк заметок в конце (// NOTE: ...).

Полезные фрагменты из базы знаний:
{context}
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
| Назначение | | |
| Когда применять | | |
| Ключевые параметры | | |
| Ограничения | | |
| Типовая стратегия-сосед | | |

После таблицы — 2–4 строки «Практический вывод»: что выбрать в каких случаях.
Опирайся ТОЛЬКО на контекст ниже. Если данных по какому-то объекту нет —
поставь в ячейке «нет данных в документации» и Ничего не придумывай.

Контекст:
{context}
"""


# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------
def _render(prompt: str, context: str) -> str:
    """Подставляет контекст в промпт.

    Через str.replace, а не str.format: в промпте про PML есть фигурные скобки
    синтаксиса (`IF $x == "y" { ... }`), и format() на них падает.
    """
    return prompt.replace("{context}", context)


def _format_hits(hits: list[dict], numbered: bool = True) -> str:
    """Склеивает фрагменты в контекст для промпта (с нумерацией для ссылок)."""
    if not hits:
        return "(пусто — релевантных фрагментов не найдено)"
    parts: list[str] = []
    for i, h in enumerate(hits, 1):
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
        prompt = _render(SYSTEM_PROMPT_CHAT, _format_hits(hits))
        answer = self._generate(LLM_MODEL, f"{prompt}\n\nВопрос технолога: {query}\n\nОтвет эксперта:")
        return f"{answer}\n\n{_format_sources(hits)}"

    def macro(self, task: str, save: bool = True) -> str:
        """Генерация PML-макроса + сохранение в output/macros."""
        hits = self._retrieve(task, top_k=max(TOP_K, 5))
        prompt = _render(SYSTEM_PROMPT_MACRO, _format_hits(hits))
        code = self._generate(LLM_CODE_MODEL,
                              f"{prompt}\n\nЗадача: {task}\n\nКод PML:", temperature=0.3)
        out = f"⚙️ PML-макрос по задаче: {task}\n\n{code}"
        if save:
            path = save_macro(code, task)
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
        prompt = _render(SYSTEM_PROMPT_COMPARE, _format_hits(hits))
        answer = self._generate(
            LLM_MODEL,
            f"{prompt}\n\nСравни «{left}» и «{right}».\n\nОтвет:",
        )
        return f"{answer}\n\n{_format_sources(hits)}"

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
def save_macro(text: str, task: str) -> Path | None:
    """Вытаскивает код из ответа LLM и сохраняет в выходную папку."""
    try:
        from config import OUTPUT_DIR

        folder = OUTPUT_DIR / "macros"
        folder.mkdir(parents=True, exist_ok=True)
        code = extract_code(text)
        if not code.strip():
            return None
        slug = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", "_", task.strip())[:40].strip("_") or "macro"
        path = folder / f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}.mac"
        path.write_text(code, encoding="utf-8")
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

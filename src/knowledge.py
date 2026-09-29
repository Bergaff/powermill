"""
Знания о твоей работе: правила и уроки «ошибка → что поправил».

Что это и зачем
---------------
Это то, что ты называешь обучением: ассистент должен понимать, **как работаешь
именно ты** — какие режимы ставишь, какие стратегии берёшь, что делать, когда
PowerMill ругается. Дообучать модель для этого не нужно: знания лежат обычными
файлами рядом с данными и подмешиваются в ответ.

    DATA_ROOT\\knowledge\\rules.md       правила — простым текстом, правятся руками
    DATA_ROOT\\knowledge\\lessons.jsonl  уроки «что было не так и что помогло»

Правила: одна строка — одно правило. Строки, начинающиеся с `#`, — это заголовки
разделов (для читаемости), они правилами не считаются.

    ## Материалы
    - 40Х, фреза D16 z4: S=4500 F=1200, ap=8
    - обдирку всегда делаю Model Area Clearance, потом чистовую

Уроки пишутся сами: если прогон (поток, проверки, вывод NC) закончился не
идеально, ассистент один раз спрашивает «что поправил» и запоминает ответ.
Если всё прошло хорошо — не спрашивает (чтобы не надоедать).

ГЛАВНОЕ: НИЧЕГО ИЗ ЭТИХ ФАЙЛОВ НЕ УХОДИТ В ОБЛАКО
--------------------------------------------------
Из правил и уроков видно твои детали, материалы и заказчиков. Поэтому ответ,
в котором они участвуют, считает **только локальная модель** (Ollama). Функция
`local_only()` возвращает True, пока есть хоть одно правило или урок, и в
`src/rag.py` это проверяется до обращения к платному API: при отсутствии
локальной модели ассистент честно скажет, что не ответит, вместо того чтобы
молча отправить твои данные в интернет.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import DATA_ROOT

KNOWLEDGE_DIR = DATA_ROOT / "knowledge"
RULES_FILE = KNOWLEDGE_DIR / "rules.md"
LESSONS_FILE = KNOWLEDGE_DIR / "lessons.jsonl"

# Сколько правил и уроков кладём в ответ (чтобы промпт не распух)
RULES_IN_PROMPT = 20
LESSONS_IN_PROMPT = 3
LESSON_MIN_SCORE = 2                     # хотя бы два общих слова — иначе не лезем

MAX_LESSON_CHARS = 1200                  # защита от гигантских вставок


# --------------------------------------------------------------------------
# Правила
# --------------------------------------------------------------------------
def rules_path() -> Path:
    return RULES_FILE


def ensure_files() -> None:
    """Создаёт файлы знаний с понятной шапкой (если их ещё нет)."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if not RULES_FILE.exists():
        RULES_FILE.write_text(
            "# Правила работы: как делаешь ты\n"
            "#\n"
            "# Одна строка — одно правило. Так ассистент будет отвечать «как у тебя»,\n"
            "# а не «в среднем по интернету». Заголовки (#) правилами не считаются.\n"
            "#\n"
            "# ВАЖНО: эти строки в облако не уходят — ответы, где они\n"
            "# участвуют, считает только локальная модель (Ollama) у тебя на ПК.\n"
            "#\n"
            "# Примеры (раскомментируй или напиши своё):\n"
            "# - 40Х, фреза D16 z4: S=4500 F=1200, ap=8\n"
            "# - обдирку делаю Model Area Clearance, потом чистовую\n"
            "# - державку ставлю от патрона BT40\n"
            "# - в NC сначала идёт самый большой диаметр\n"
            "# - имена траекторий: OPER_01_OBR, OPER_02_POLUCH\n"
            "#\n"
            "# Править можно и здесь, и пунктом 48 меню.\n",
            encoding="utf-8")
    if not LESSONS_FILE.exists():
        LESSONS_FILE.write_text(
            "# Уроки «что было не так и что помогло». Одна строка — один урок (JSON).\n"
            "# Их пишет ассистент сам после неудачных прогонов; можно добавить руками\n"
            "# (пункт 48 меню). Подробности — в README, раздел «Знания о твоей работе».\n",
            encoding="utf-8")


def load_rules() -> list[str]:
    """Правила по порядку (без заголовков и комментариев)."""
    if not RULES_FILE.exists():
        return []
    try:
        text = RULES_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rules: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*•]\s*", "", line)         # маркер списка — не правило
        line = re.sub(r"^\d+[.)]\s*", "", line)
        if line:
            rules.append(line)
    return rules


def add_rule(text: str) -> Path:
    """Добавляет правило (одной строкой)."""
    clean = " ".join((text or "").split())
    if not clean:
        raise ValueError("пустое правило")
    ensure_files()
    with RULES_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"- {clean}\n")
    return RULES_FILE


def remove_rule(index: int) -> str:
    """Удаляет правило по номеру (1 — первое). Возвращает, что удалили."""
    rules = load_rules()
    if not 1 <= index <= len(rules):
        raise IndexError(f"правила №{index} нет: всего {len(rules)}")
    removed = rules.pop(index - 1)
    write_rules(rules)
    return removed


def write_rules(rules: list[str]) -> Path:
    """Перезаписывает список правил (заголовки при этом теряются — пишем свои)."""
    ensure_files()
    body = ["# Правила работы: как делаешь ты", ""]
    body += [f"- {rule}" for rule in rules]
    RULES_FILE.write_text("\n".join(body) + "\n", encoding="utf-8")
    return RULES_FILE


# --------------------------------------------------------------------------
# Уроки
# --------------------------------------------------------------------------
@dataclass
class Lesson:
    """Один урок: что делали, что пошло не так и что помогло."""

    when: str = ""
    source: str = ""                 # откуда: make_flow / check_toolpaths / make_nc / вручную
    task: str = ""                   # что делали
    problem: str = ""                # что пошло не так (строки отчёта)
    fix: str = ""                    # что поправил (ответ технолога)
    tags: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (f"{self.when} | {self.source} | {self.task} | "
                f"{self.problem} | {self.fix}")

    def format(self) -> str:
        head = f"[{self.when}] {self.source or 'вручную'}"
        parts = [head]
        if self.task:
            parts.append(f"  дело: {self.task}")
        if self.problem:
            parts.append(f"  было не так: {self.problem}")
        if self.fix:
            parts.append(f"  помогло: {self.fix}")
        return "\n".join(parts)


def load_lessons() -> list[Lesson]:
    """Все уроки по порядку (битые строки пропускаем — файл правят руками)."""
    if not LESSONS_FILE.exists():
        return []
    try:
        text = LESSONS_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lessons: list[Lesson] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        known = {key: data[key] for key in Lesson.__dataclass_fields__  # type: ignore[attr-defined]
                 if key in data}
        known.setdefault("tags", [])
        if not isinstance(known["tags"], list):
            known["tags"] = []
        lessons.append(Lesson(**known))
    return lessons


def add_lesson(problem: str = "", fix: str = "", task: str = "",
               source: str = "", when: str = "") -> Lesson:
    """Записывает урок (одна строка JSON — файл не ломается при обрыве)."""
    ensure_files()
    lesson = Lesson(
        when=when or time.strftime("%Y-%m-%d %H:%M"),
        source=source,
        task=(task or "").strip()[:MAX_LESSON_CHARS // 3],
        problem=(problem or "").strip()[:MAX_LESSON_CHARS],
        fix=(fix or "").strip()[:MAX_LESSON_CHARS],
        tags=_tags(f"{task} {problem} {fix}"),
    )
    with LESSONS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(lesson), ensure_ascii=False) + "\n")
    return lesson


STOP_WORDS = {
    "и", "в", "не", "на", "с", "по", "для", "что", "как", "это", "ни", "из",
    "или", "а", "но", "же", "уже", "всё", "все", "так", "the", "and", "for",
}


# Слова сравниваем «по основе»: у русского слова много форм («державка» и
# «державку» — одно и то же), а полноценная морфология тут не нужна. Обрезаем
# слово до первых букв — этого достаточно, чтобы похожие случаи находились.
STEM_LENGTH = 6


def _words(text: str) -> set[str]:
    """Основы слов для сравнения (русские/латинские, от 3 букв)."""
    found = re.findall(r"[а-яёa-z0-9]{3,}", (text or "").lower())
    words = set()
    for word in found:
        if word in STOP_WORDS:
            continue
        words.add(word[:STEM_LENGTH] if len(word) > STEM_LENGTH else word)
    return words


def _tags(text: str, limit: int = 8) -> list[str]:
    """Короткие метки урока — по ним потом ищем похожие."""
    counts: dict[str, int] = {}
    for word in _words(text):
        counts[word] = counts.get(word, 0) + 1
    return sorted(counts, key=lambda word: (-counts[word], word))[:limit]


def similar_lessons(query: str, limit: int = LESSONS_IN_PROMPT) -> list[Lesson]:
    """Уроки, похожие на текущую задачу (по совпадению слов)."""
    words = _words(query)
    if not words:
        return []
    scored: list[tuple[int, int, Lesson]] = []
    for index, lesson in enumerate(load_lessons()):
        lesson_words = _words(f"{lesson.task} {lesson.problem} {lesson.fix}")
        score = len(words & lesson_words)
        if score >= LESSON_MIN_SCORE:
            scored.append((score, -index, lesson))       # при равенстве — свежие
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [lesson for _score, _index, lesson in scored[:limit]]


# --------------------------------------------------------------------------
# Что попадает в ответ модели
# --------------------------------------------------------------------------
def prompt_block(question: str = "", rules_limit: int = RULES_IN_PROMPT,
                 lessons_limit: int = LESSONS_IN_PROMPT) -> str:
    """Блок знаний для промпта: правила + похожие уроки. Пусто — если знаний нет."""
    parts: list[str] = []
    rules = load_rules()
    if rules:
        shown = rules[:rules_limit]
        parts.append("ПРАВИЛА ТЕХНОЛОГА (это его собственные правила — соблюдай):\n"
                     + "\n".join(f"  - {rule}" for rule in shown))
        if len(rules) > len(shown):
            parts.append(f"  (…ещё {len(rules) - len(shown)} правил: "
                         f"{RULES_FILE})")

    lessons = similar_lessons(question, limit=lessons_limit) if question else []
    if lessons:
        text = "\n".join(f"  {index}. {lesson.format()}"
                         for index, lesson in enumerate(lessons, 1))
        parts.append("ПОХОЖИЕ СЛУЧАИ ИЗ ЕГО РАБОТЫ (чем раньше кончилось):\n" + text)

    if not parts:
        return ""
    return ("ЗНАНИЯ О РАБОТЕ ТЕХНОЛОГА (файлы у него на компьютере, "
            "в облако не отправлялись):\n" + "\n\n".join(parts))


def local_only() -> bool:
    """Нужно ли считать ответ только локальной моделью.

    Правила и уроки описывают реальные детали, материалы и заказы. Пока они
    есть, ответ с ними идёт мимо облака — это не «настройка», а обещание.
    """
    return bool(load_rules()) or bool(load_lessons())


def use_local(question: str = "") -> bool:
    """Понадобятся ли знания именно для этого вопроса."""
    if load_rules():
        return True
    return bool(similar_lessons(question))


def stats() -> dict:
    """Сколько знаний собрано — для меню и отчёта доктора."""
    rules = load_rules()
    lessons = load_lessons()
    return {
        "rules": len(rules),
        "lessons": len(lessons),
        "rules_file": RULES_FILE,
        "lessons_file": LESSONS_FILE,
        "folder": KNOWLEDGE_DIR,
        "local_only": local_only(),
    }


def format_stats() -> str:
    data = stats()
    lines = [
        f"Правил: {data['rules']}",
        f"Уроков: {data['lessons']}",
        f"Папка знаний: {data['folder']}",
    ]
    if data["local_only"]:
        lines.append("Ответы с этими знаниями считает ТОЛЬКО локальная модель "
                     "(Ollama): твои данные в облако не уходят.")
    else:
        lines.append("Знаний пока нет — ассистент отвечает как раньше. "
                     "Добавь первое правило: пункт 48 меню.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Урок из неудачного прогона
# --------------------------------------------------------------------------
def ask_lesson(problems: list[str], task: str = "", source: str = "",
               reader=None, printer=print) -> Lesson | None:
    """Спрашивает «что поправил» после неудачного прогона и записывает урок.

    Вызывается только когда что-то пошло не так (поток написал «НЕ всё
    сделано», проверки нашли замечания, файл NC не появился). Если технолог
    нажал Enter — ничего не записываем: пустых уроков не бывает.

    `reader` — функция чтения строки (по умолчанию `src.console.read_line`),
    `printer` — куда печатать (в тестах подменяются).
    """
    if not problems:
        return None
    if reader is None:
        from src.console import read_line as reader          # noqa: PLC0415

    printer("")
    printer("  Что-то пошло не так. Чтобы в следующий раз ассистент это знал:")
    printer("  напиши, что ты поправил (Enter — не записывать).")
    try:
        answer = reader("  Что поправил: ")
    except (EOFError, KeyboardInterrupt):
        return None
    if answer is None:
        return None
    fix = " ".join((answer or "").split())
    if not fix:
        printer("  Ничего не записал.")
        return None
    lesson = add_lesson(problem="; ".join(problems)[:MAX_LESSON_CHARS],
                        fix=fix, task=task, source=source)
    printer(f"  Запомнил: {LESSONS_FILE}")
    printer("  (Файл у тебя; в облако это не уходит — считает локальная модель.)")
    return lesson


def main() -> int:
    """Проверка вручную: python -m src.knowledge"""
    print(format_stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

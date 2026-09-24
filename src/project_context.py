"""
Контекст проекта PowerMill: «что у тебя открыто прямо сейчас».

Зачем
-----
Самый большой минус консольного ассистента: он не знает твоего проекта.
Поэтому макросы и подсказки получаются «в вакууме» — с абстрактными именами
вместо настоящих.

Как это решается без плагина (шаг 2.0 плана):

1. Макрос `output\\PM_PROBE.mac` печатает в окно сообщений PowerMill списки
   объектов проекта (модели, границы, инструменты, траектории, плоскости,
   NC-программы).
2. Ты копируешь этот текст (или пункт 24 меню — он открывает блокнот, куда
   его удобно вставить) — ассистент разбирает его в `output\\project_context.json`.
3. Дальше ассистент ВЕЗДЕ использует твои имена: `/macro`, `/ask`, `/project`.

Дополнительно модуль делает проверки по снимку (первый кусок Уровня 3):
имена-заглушки, дубликаты, траектории без инструментов и NC-программ —
то, что видно по структуре проекта и реально помогает навести порядок.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from config import OUTPUT_DIR

CONTEXT_FILE = OUTPUT_DIR / "project_context.json"
DUMP_FILE = OUTPUT_DIR / "project_dump.txt"

# Заголовки разделов: как их печатает макрос-разведчик (и как пишет человек)
SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "models": ("MODELS", "MODEL", "МОДЕЛИ", "МОДЕЛЬ"),
    "stockmodels": ("STOCK MODELS", "STOCKMODELS", "STOCKMODEL", "ЗАГОТОВКИ", "ЗАГОТОВКА"),
    "boundaries": ("BOUNDARIES", "BOUNDARY", "ГРАНИЦЫ", "ГРАНИЦА"),
    "patterns": ("PATTERNS", "PATTERN", "ШАБЛОНЫ", "ШАБЛОН"),
    "tools": ("TOOLS", "TOOL", "ИНСТРУМЕНТЫ", "ИНСТРУМЕНТ", "ФРЕЗЫ"),
    "toolpaths": ("TOOLPATHS", "TOOLPATH", "ТРАЕКТОРИИ", "ТРАЕКТОРИЯ"),
    "workplanes": ("WORKPLANES", "WORKPLANE", "ПЛОСКОСТИ", "РАБОЧИЕ ПЛОСКОСТИ"),
    "ncprograms": ("NC PROGRAMS", "NC PROGRAMS", "NCPROGRAMS", "NCPROGRAM",
                   "NC-ПРОГРАММЫ", "ПРОГРАММЫ", "УП"),
    "machinetools": ("MACHINE TOOLS", "MACHINETOOLS", "MACHINETOOL", "СТАНКИ"),
    "features": ("FEATURE SETS", "FEATURES", "FEATURE", "ЭЛЕМЕНТЫ"),
    "levels": ("LEVELS", "УРОВНИ"),
}

# Обратный словарь: нормализованный заголовок -> раздел
_HEADER_INDEX: dict[str, str] = {}
for _section, _keys in SECTION_KEYS.items():
    for _key in _keys:
        _HEADER_INDEX[_key] = _section
_HEADER_INDEX["NC PROGRAM"] = "ncprograms"

HEADER_RE = re.compile(r"^([A-Za-zА-Яа-я][A-Za-zА-Яа-я \-]{1,24})\s*:?\s*$")
KV_RE = re.compile(r"^(MODEL|BOUNDARY|TOOL|TOOLPATH|WORKPLANE|NCPROGRAM|"
                   r"STOCKMODEL|PATTERN)\s*=\s*(.+)$", re.I)
NOISE_PREFIXES = ("---", "//", "PRINT", "POWERMILL AI PROBE", "ВЕРСИЯ", "VERSION")
PLACEHOLDER_RE = re.compile(
    r"^(model|boundary|tool|toolpath|workplane|ncprogram|stockmodel|pattern|"
    r"модель|граница|инструмент|траектория|плоскость)"
    r"[\s_\-]*\d*$", re.I)


# --------------------------------------------------------------------------
# Разбор текста снимка
# --------------------------------------------------------------------------
def _clean_name(raw: str) -> str:
    name = raw.strip().strip("«»\"'")
    name = re.sub(r"^[-*>\s]+", "", name)
    return name.strip()


def parse_dump(text: str) -> dict:
    """Разбирает вывод макроса-разведчика в структуру проекта.

    Понимает оба формата:
      * «раздел + список строк» (как печатает PM_PROBE.mac);
      * «KEY=значение» (короткий формат прошлых версий макроса).
    """
    data = {section: [] for section in SECTION_KEYS}
    current: str | None = None
    unparsed: list[str] = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        upper = line.upper().rstrip(":")
        if any(upper.startswith(prefix.upper()) for prefix in NOISE_PREFIXES):
            continue

        kv = KV_RE.match(line)
        if kv:
            key = "ncprograms" if kv.group(1).upper() == "NCPROGRAM" else \
                next((s for s in SECTION_KEYS
                      if kv.group(1).upper() in SECTION_KEYS[s]), "models")
            name = _clean_name(kv.group(2))
            if name:
                data[key].append(name)
            continue

        header = HEADER_RE.match(upper)
        if header:
            key = _HEADER_INDEX.get(header.group(1).strip())
            if key:
                current = key
                continue
            # неизвестный заголовок — возможно, это имя объекта с двоеточием
            if line.endswith(":"):
                unparsed.append(line)
                continue

        name = _clean_name(line)
        if not name:
            continue
        if current:
            data[current].append(name)
        else:
            unparsed.append(name)

    result = {section: names for section, names in data.items() if names}
    if unparsed:
        result["_unparsed"] = unparsed[:50]
    total = sum(len(v) for k, v in result.items() if not k.startswith("_"))
    result["_total"] = total
    result["_parsed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return result


# --------------------------------------------------------------------------
# Хранение
# --------------------------------------------------------------------------
def save(context: dict) -> Path:
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(json.dumps(context, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    return CONTEXT_FILE


def load() -> dict | None:
    if not CONTEXT_FILE.exists():
        return None
    try:
        return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clear() -> None:
    for path in (CONTEXT_FILE, DUMP_FILE):
        try:
            path.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Тексты для человека и для модели
# --------------------------------------------------------------------------
SECTION_TITLES = {
    "models": "Модели", "stockmodels": "Заготовки", "boundaries": "Границы",
    "patterns": "Шаблоны", "tools": "Инструменты", "toolpaths": "Траектории",
    "workplanes": "Рабочие плоскости", "ncprograms": "NC-программы",
    "machinetools": "Станки", "features": "Элементы", "levels": "Уровни",
}


def summary(context: dict | None = None, limit: int = 40) -> str:
    """Короткая сводка: что нашлось в проекте."""
    context = context if context is not None else load()
    if not context:
        return ("Снимок проекта ещё не загружен.\n"
                "  Запусти пункт 24 меню и вставь то, что напечатает макрос "
                "разведки в PowerMill.")

    lines = [f"Проект PowerMill (снимок от {context.get('_parsed_at', '?')}):"]
    for section, title in SECTION_TITLES.items():
        names = context.get(section) or []
        if not names:
            continue
        shown = ", ".join(names[:limit])
        more = f" … ещё {len(names) - limit}" if len(names) > limit else ""
        lines.append(f"  {title} ({len(names)}): {shown}{more}")
    if not any(context.get(s) for s in SECTION_TITLES):
        lines.append("  Объектов не видно — возможно, проект пустой или снимок неполный.")
    return "\n".join(lines)


def to_prompt_block(context: dict | None = None, limit: int = 25) -> str:
    """Блок для промпта модели: настоящие имена объектов технолога."""
    context = context if context is not None else load()
    if not context:
        return ""
    parts = ["Проект технолога (реальные имена — используй их в коде и ответах):"]
    for section, title in SECTION_TITLES.items():
        names = context.get(section) or []
        if not names:
            continue
        shown = ", ".join(f'"{n}"' for n in names[:limit])
        parts.append(f"  {title}: {shown}")
    return "\n".join(parts) if len(parts) > 1 else ""


# --------------------------------------------------------------------------
# Проверки по снимку (первый кусок Уровня 3)
# --------------------------------------------------------------------------
def checks(context: dict | None = None) -> list[dict]:
    """Проверки структуры проекта. Возвращает список {level, text, hint}."""
    context = context if context is not None else load()
    if not context:
        return []

    found: list[dict] = []

    def warn(text: str, hint: str = "") -> None:
        found.append({"level": "warn", "text": text, "hint": hint})

    def note(text: str, hint: str = "") -> None:
        found.append({"level": "note", "text": text, "hint": hint})

    models = context.get("models") or []
    tools = context.get("tools") or []
    toolpaths = context.get("toolpaths") or []
    boundaries = context.get("boundaries") or []
    ncprograms = context.get("ncprograms") or []
    workplanes = context.get("workplanes") or []

    if not models:
        note("В снимке нет моделей — либо проект пустой, либо разведка не увидела их.",
             "Открой проект в PowerMill и запусти output\\PM_PROBE.mac заново.")
    if toolpaths and not tools:
        warn(f"Траекторий {len(toolpaths)}, а инструментов нет.",
             "Проверь, что макрос разведки выполнился полностью (окно сообщений).")
    if toolpaths and not ncprograms:
        note(f"Траекторий {len(toolpaths)}, но NC-программ нет.",
             "Пока не создана NC-программа, траектории не выведены на станок.")
    if toolpaths and not boundaries:
        note("Границ нет — траектории считаются по модели целиком.",
             "Для черновой по заготовке обычно нужна граница (Boundary).")
    if toolpaths and not workplanes:
        note("Рабочих плоскостей в снимке нет.",
             "Для 3+2 и 5-осевых операций плоскости нужны заранее.")

    # имена-заглушки: с ними неудобно писать макросы и опасно править вручную
    for section, title in (("toolpaths", "траекторий"), ("boundaries", "границ"),
                           ("tools", "инструментов")):
        placeholders = [n for n in (context.get(section) or [])
                        if PLACEHOLDER_RE.match(n)]
        if len(placeholders) >= 3:
            warn(f"Много имён-заглушек среди {title}: "
                 f"{', '.join(placeholders[:5])}",
                 "Переименуй по смыслу (например «Rough_D16_40X») — "
                 "макросы и подсказки станут точными.")

    # дубликаты имён внутри раздела
    for section, title in SECTION_TITLES.items():
        names = context.get(section) or []
        seen: set[str] = set()
        dups = {n for n in names if n.lower() in seen or seen.add(n.lower())}
        if dups:
            warn(f"Повторяющиеся имена среди «{title}»: {', '.join(sorted(dups)[:5])}",
                 "PowerMill различает объекты по именам — проверь, нет ли путаницы.")

    if not found:
        note("Структура проекта выглядит аккуратно.", "")
    return found


def format_checks(context: dict | None = None) -> str:
    """Проверки в виде текста для чата."""
    context = context if context is not None else load()
    if not context:
        return ""
    items = checks(context)
    if not items:
        return ""
    lines = ["🔍 Проверка проекта:"]
    for item in items:
        mark = "⚠️" if item["level"] == "warn" else "•"
        lines.append(f"  {mark} {item['text']}")
        if item["hint"]:
            lines.append(f"      → {item['hint']}")
    return "\n".join(lines)


def main() -> int:
    """Разбор файла снимка: python -m src.project_context [файл]."""
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DUMP_FILE
    if not path.exists():
        print(f"(!) Нет файла {path}")
        print("    Вставь вывод макроса разведки в этот файл (пункт 24 меню).")
        return 2

    context = parse_dump(path.read_text(encoding="utf-8", errors="replace"))
    if context.get("_total", 0) == 0:
        print("(!) В тексте не нашлось ни одного объекта проекта.")
        print("    Скопируй строки между «POWERMILL AI PROBE START» и «…END».")
        return 3

    saved = save(context)
    print(summary(context))
    print()
    checks_text = format_checks(context)
    if checks_text:
        print(checks_text)
    print(f"\n💾 Сохранено: {saved}")
    print("   Теперь ассистент знает твои имена: /macro, /ask, /project")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

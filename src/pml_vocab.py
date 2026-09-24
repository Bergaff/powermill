"""
Словарь реального PML и проверка сгенерированных макросов.

Зачем
-----
Языковая модель охотно пишет «красивый» PML, которого не существует:

    Create Boundary "Silhouette" $e
    Add Default Allowance $e

Такие строки выглядят правдоподобно, но PowerMill их не выполнит. Поэтому:

1. Из РАЗОБРАННОЙ документации собираем словарь настоящих имён:
   * типы объектов PML — из имён файлов справочника (PARREF: `toolpath`,
     `boundary`, `tool`, `model`, `ncprogram`, …);
   * имена параметров — из заголовков справочника (PARREF/PARSUM);
   * источники — страницы справки про макросы.
   Словарь: `output/pml_vocabulary.json` (+ .txt для чтения человеком).

2. После генерации макроса проверяем его по словарю: неизвестные типы
   объектов, «команды»-самозванцы и подозрительные строки попадают в отчёт,
   который пользователь видит прямо в чате.

Модуль намеренно осторожен: цель — не «запретить всё», а показать, каким
строкам макроса нельзя верить без проверки в PowerMill.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from config import OUTPUT_DIR

VOCAB_FILE = OUTPUT_DIR / "pml_vocabulary.json"
VOCAB_TEXT = OUTPUT_DIR / "pml_vocabulary.txt"

# Реальные ключевые слова и команды PML. Регистр обязателен — в PML он значим.
KEYWORDS = frozenset("""
CREATE DELETE EDIT ACTIVATE DEACTIVATE RENAME COPY MOVE IMPORT EXPORT
FOREACH IF ELSE ELSEIF ENDIF WHILE DO ENDWHILE MACRO CALL RETURN BREAK
ENTITY ENTITYLIST FOLDER MODEL TOOLPATH TOOL BOUNDARY PATTERN WORKPLANE
STOCKMODEL NCPROGRAM SETUP FEATURE GROUP LEVEL MACHINETOOL SIMULATIONSTATE
POWERMILL PARAMETERS MEMBERS SIZE EXISTS ACTIVE SELECTED LOCKED
TRUE FALSE NULL AND OR NOT IN
STRING REAL INT INTEGER OBJECT BOOLEAN LIST PRINT MESSAGE FORMAT
SET GET ADD REMOVE APPEND CLEAR LOCK UNLOCK
ABORT EXIT STOP PAUSE PING TRACEFILE EXECUTE DOCOMMAND
FILE OPEN CLOSE READ WRITE TO AS FROM APPEND DELETE INPUT CHOICE QUERY
INFO WARN CRLF OLE FILEACTION DIALOGS ON OFF
""".split())

# Типы объектов, которые есть в любом PowerMill. Нужны как аварийный список,
# если справка ещё не разобрана (тогда словарь пуст).
FALLBACK_ENTITIES = (
    "boundary tool toolpath model pattern workplane stockmodel ncprogram "
    "setup feature group level machinetool simulationstate ncpfile macro "
    "powermill boundarycreate"
).split()

# Слова, которые встречаются в верхнем регистре, но не являются командами:
# единицы измерения, названия кнопок, служебное
KEYWORD_NOISE = frozenset(
    "MM MM_MIN RPM HRC HB KM KW RAD DEG ABS REL XYZ XY ZX YZ X Y Z OK "
    "PML NC CNC CAD CAM STEP IGES STL DXF PDF TXT DGN DUCTPOST AUTODESK".split()
)

# Что считаем командой-началом строки. Если строка начинается с другого
# ALL-CAPS слова — скажем пользователю, что это не похоже на PML.
STATEMENT_STARTERS = frozenset(
    "CREATE DELETE EDIT ACTIVATE DEACTIVATE RENAME COPY MOVE IMPORT EXPORT "
    "FOREACH IF ELSE ELSEIF ENDIF WHILE DO ENDWHILE MACRO CALL RETURN BREAK "
    "CONTINUE ENTITY PRINT MESSAGE ABORT EXIT STOP PAUSE PING TRACEFILE "
    "EXECUTE SET GET ADD REMOVE APPEND CLEAR LOCK UNLOCK STRING REAL INTEGER "
    "OBJECT BOOLEAN LIST INT FILE OLE INPUT DIALOGS FUNCTION".split()
)

# Создать/удалить/редактировать можно только объект известного типа.
ENTITY_COMMANDS = ("CREATE", "DELETE", "EDIT", "ACTIVATE", "DEACTIVATE", "SELECT")

TYPE_RE = re.compile(r"""["']([A-Za-z_]{3,30})["']""")
# после типа объекта у CREATE/DELETE аргументов быть не должно
CREATE_ARGS_RE = re.compile(
    r"\b(CREATE|DELETE)\s+([A-Za-z_]{3,30})\s+([^;{}]+)", re.I)
CREATE_RE = re.compile(r"\b(CREATE|DELETE|EDIT|ACTIVATE|DEACTIVATE)\s+([A-Za-z_]{3,30})")
QUOTED_TYPE_CMP_RE = re.compile(
    r"""\b(Type|type)\s*==\s*["']([A-Za-z_]{3,30})["']""")
STARTER_RE = re.compile(r"^([A-Za-z_]{2,30})\b")
UPPER_WORD_RE = re.compile(r"\b([A-Z][A-Z_]{2,30})\b")
HEADING_RE = re.compile(r"(?m)^#{1,3}\s+(.+)$")
CAMEL_RE = re.compile(r"^[A-Z][A-Za-z0-9_]{2,40}$")


# --------------------------------------------------------------------------
# Сборка словаря из разобранной справки
# --------------------------------------------------------------------------
def build_vocabulary(pages: list[dict]) -> dict:
    """Строит словарь настоящих имён PML из списка разобранных страниц."""
    entities: set[str] = set()
    parameters: set[str] = set()
    sources: list[dict] = []

    for page in pages:
        kind = page.get("kind", "")
        path = str(page.get("path", ""))
        if kind == "pml" or "/PARREF" in path.upper() or "/PARSUM" in path.upper():
            # имя файла справочника = имя типа объекта: toolpath.html -> toolpath
            stem = Path(path.split("#")[0]).stem
            if stem and re.fullmatch(r"[a-z][a-z0-9_]{2,30}", stem):
                entities.add(stem)
            for head in HEADING_RE.findall(page.get("text", "")):
                head = head.strip()
                if CAMEL_RE.match(head) and not head.isupper():
                    parameters.add(head)
        elif kind == "macro":
            sources.append({
                "source": page.get("source", ""),
                "title": page.get("title", ""),
            })

    # объекты, о которых точно говорится в справке руководства
    if not entities:
        entities.update(FALLBACK_ENTITIES)

    return {
        "entities": sorted(entities),
        "parameters": sorted(parameters)[:5000],
        "macro_sources": sources,
        "built_from_pages": len(pages),
    }


def save_vocabulary(vocab: dict) -> Path:
    VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOCAB_FILE.write_text(json.dumps(vocab, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    lines = [
        "Словарь реального PML (собран из документации PowerMill)",
        "=" * 58,
        f"Страниц использовано: {vocab.get('built_from_pages', 0)}",
        f"Типов объектов: {len(vocab.get('entities', []))}",
        f"Имён параметров: {len(vocab.get('parameters', []))}",
        "",
        "ТИПЫ ОБЪЕКТОВ (создаются командами CREATE/DELETE/EDIT):",
        "  " + ", ".join(vocab.get("entities", [])),
        "",
        "ПЕРВЫЕ 200 ИМЁН ПАРАМЕТРОВ:",
    ]
    params = vocab.get("parameters", [])
    for i in range(0, min(len(params), 200), 6):
        lines.append("  " + ", ".join(params[i:i + 6]))
    if vocab.get("macro_sources"):
        lines += ["", "НАЙДЕННЫЕ МАКРОСЫ:"]
        lines += [f"  {m['title']}  ->  {m['source']}" for m in vocab["macro_sources"][:50]]
    VOCAB_TEXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return VOCAB_FILE


def load_vocabulary() -> dict:
    """Читает словарь; если его нет — аварийный список типов объектов."""
    try:
        return json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entities": list(FALLBACK_ENTITIES), "parameters": [],
                "macro_sources": [], "built_from_pages": 0}


# --------------------------------------------------------------------------
# Подбор имён под задачу (для подсказки модели)
# --------------------------------------------------------------------------
_RU_STOP = frozenset(
    "все всеx для и в на с по из от до за не что как это модель модели "
    "создать создать создать добавить удалить найти сделать нужно надо "
    "всех каждом каждый границы граница траектории траектория".split())


def relevant_entities(query: str, vocab: dict, limit: int = 40) -> list[str]:
    """Типы объектов, похожие на слова из запроса + самые ходовые."""
    entities = vocab.get("entities") or list(FALLBACK_ENTITIES)
    words = {w for w in re.findall(r"[a-zA-Zа-яА-Я_]{3,}", query.lower())}
    ru_words = {w for w in words if re.search(r"[а-я]", w)} - _RU_STOP

    # русские слова -> английские синонимы из словаря частых терминов
    mapped: set[str] = set()
    for ru in ru_words:
        mapped.update(_RU_TO_EN.get(ru, ()))

    scored: list[tuple[int, str]] = []
    for entity in entities:
        name = entity.lower()
        score = 0
        if name in words:
            score += 5
        with_score = 0
        for ru in ru_words:
            if ru[:4] in name or name[:4] in ru:
                score += 2
                with_score += 1
        if mapped and any(m in name for m in mapped):
            score += 4
        scored.append((score, entity))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _s, name in scored[:limit]]


# Мини-словарь русских технических слов на английский PML-корень
_RU_TO_EN = {
    "границы": ("boundary",), "граница": ("boundary",),
    "траектория": ("toolpath",), "траектории": ("toolpath",),
    "инструмент": ("tool",), "фреза": ("tool",),
    "модель": ("model",), "модели": ("model",),
    "заготовка": ("stockmodel", "block"),
    "макрос": ("macro",), "наладка": ("setup",), "установ": ("setup",),
    "программа": ("ncprogram", "program"), "шаблон": ("pattern",),
    "плоскость": ("workplane",), "рабочая": ("workplane",),
    "станок": ("machinetool",), "моделирование": ("simulation",),
    "элемент": ("feature",), "компонент": ("component",),
}


def relevant_parameters(query: str, hits: list[dict], vocab: dict,
                        limit: int = 60) -> list[str]:
    """Имена параметров, встречающиеся в найденных фрагментах справочника."""
    from_hits: list[str] = []
    for hit in hits:
        for head in HEADING_RE.findall(hit.get("text", "")):
            head = head.strip()
            if CAMEL_RE.match(head) and not head.isupper() and head not in from_hits:
                from_hits.append(head)
    if from_hits:
        return from_hits[:limit]
    return (vocab.get("parameters") or [])[:limit]


# --------------------------------------------------------------------------
# Проверка макроса
# --------------------------------------------------------------------------
def validate(code: str, vocab: dict | None = None) -> dict:
    """Проверяет текст макроса по словарю реального PML.

    Возвращает словарь с ключами:
      ok            — подозрительных строк не найдено
      unknown_types — CREATE/EDIT/DELETE с несуществующим типом объекта
      bad_types     — сравнения Type == "Чегото" с несуществующим типом
      not_commands  — строки, которые не похожи ни на одну команду PML
      case_errors   — команда есть, но не заглавными буквами (PML значим регистр)
      bad_arity     — у CREATE/DELETE лишние аргументы после типа объекта
      foreign_upper — прочие ALL-CAPS слова, которых нет в языке
      lines         — исходные строки для показа пользователю
    """
    vocab = vocab or load_vocabulary()
    known = {e.lower() for e in vocab.get("entities", [])}
    known |= {k.lower() for k in KEYWORDS}
    known |= {e.lower() for e in FALLBACK_ENTITIES}

    unknown_types: list[tuple[int, str]] = []
    bad_types: list[tuple[int, str]] = []
    not_commands: list[tuple[int, str]] = []
    foreign_upper: list[tuple[int, str]] = []
    case_errors: list[tuple[int, str]] = []
    bad_arity: list[tuple[int, str]] = []

    in_block_comment = False
    for number, raw in enumerate(code.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
            continue
        if line.startswith("/*"):
            in_block_comment = "*/" not in line
            continue
        if line.startswith("//") or line.startswith("#"):
            continue
        # код без строковых литералов — чтобы не ловить слова из сообщений
        stripped = TYPE_RE.sub('""', line)

        for match in CREATE_RE.finditer(stripped):
            entity = match.group(2).lower()
            if entity not in known:
                unknown_types.append((number, raw))

        for match in QUOTED_TYPE_CMP_RE.finditer(line):
            value = match.group(2)
            if value.lower() not in known and not value.startswith("$"):
                bad_types.append((number, raw))

        head = STARTER_RE.match(stripped)
        if head:
            first = head.group(1)
            if first.isupper():
                if first not in STATEMENT_STARTERS and first not in KEYWORDS:
                    not_commands.append((number, raw))
            elif first[0].isupper() and first.isalpha():
                # «Add Default Allowance $e» или «Create Boundary …»
                if first.upper() in KEYWORDS:
                    # команда есть, но написана не заглавными: PML различает регистр
                    case_errors.append((number, raw))
                else:
                    not_commands.append((number, raw))

        for match in CREATE_ARGS_RE.finditer(stripped):
            tail = match.group(3).strip()
            if tail and not tail.startswith((";", "{", "}")):
                bad_arity.append((number, raw))

        for word in set(UPPER_WORD_RE.findall(stripped)):
            if (word.lower() not in known and word not in KEYWORD_NOISE
                    and not word.startswith("$")):
                foreign_upper.append((number, raw))
                break

    return {
        "ok": not (unknown_types or bad_types or not_commands
                   or case_errors or bad_arity),
        "unknown_types": unknown_types,
        "bad_types": bad_types,
        "not_commands": not_commands,
        "case_errors": case_errors,
        "bad_arity": bad_arity,
        "foreign_upper": foreign_upper,
        "entities_known": len(vocab.get("entities", [])),
        "parameters_known": len(vocab.get("parameters", [])),
    }


def format_check(report: dict) -> str:
    """Отчёт проверки для показа в чате (короткий и по делу)."""
    lines = ["🔎 Проверка макроса по документации PowerMill:"]
    total_params = report.get("parameters_known", 0)
    lines.append(f"   словарь: типов объектов {report.get('entities_known', 0)}, "
                 f"имён параметров {total_params}")

    if report["ok"]:
        lines.append("   ✅ подозрительных строк не найдено: все типы объектов "
                     "и команды есть в документации")
        if report.get("foreign_upper"):
            lines.append("   ℹ️ проверь вручную (не найдено в словаре):")
            for number, line in report["foreign_upper"][:5]:
                lines.append(f"      строка {number}: {line}")
        return "\n".join(lines)

    lines.append("   ⚠️ этим строкам НЕЛЬЗЯ верить без проверки в PowerMill:")
    if report["not_commands"]:
        lines.append("   • не похоже на команду PML:")
        for number, line in report["not_commands"][:5]:
            lines.append(f"      строка {number}: {line}")
    if report["unknown_types"]:
        lines.append("   • тип объекта, которого нет в документации:")
        for number, line in report["unknown_types"][:5]:
            lines.append(f"      строка {number}: {line}")
    if report["bad_types"]:
        lines.append("   • сравнение с типом объекта, которого нет:")
        for number, line in report["bad_types"][:5]:
            lines.append(f"      строка {number}: {line}")
    if report["case_errors"]:
        lines.append("   • команда написана не заглавными буквами "
                     "(PML различает регистр):")
        for number, line in report["case_errors"][:5]:
            lines.append(f"      строка {number}: {line}")
    if report["bad_arity"]:
        lines.append("   • у CREATE/DELETE не бывает аргументов после типа "
                     "объекта:")
        for number, line in report["bad_arity"][:5]:
            lines.append(f"      строка {number}: {line}")
    lines.append("   Запусти макрос на копии проекта или проверь строки в "
                 "справочнике (пункт 2 меню).")
    return "\n".join(lines)


def main() -> int:
    """Запуск вручную: пересобрать словарь из output/help_pages.jsonl."""
    import sys

    from config import OUTPUT_DIR as OUT

    pages_file = OUT / "help_pages.jsonl"
    if not pages_file.exists():
        print(f"(!) Нет файла {pages_file} — сначала разбери справку "
              f"(start_parse_help.bat)")
        return 2

    pages: list[dict] = []
    with pages_file.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    pages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    vocab = build_vocabulary(pages)
    save_vocabulary(vocab)
    print(f"Словарь PML: типов объектов {len(vocab['entities'])}, "
          f"параметров {len(vocab['parameters'])}")
    print(f"  {VOCAB_FILE}")
    print(f"  {VOCAB_TEXT}")

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        code = Path(sys.argv[2]).read_text(encoding="utf-8")
        print(format_check(validate(code, vocab)))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

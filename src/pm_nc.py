"""
NC-программа из траекторий (шаг 3.5, пункт 36).

Команды — из рабочих макросов Autodesk («Macro to create NC code»):

    CREATE NCPROGRAM $имя                  // создать программу
    ACTIVATE NCPROGRAM $имя                // сделать активной
    EDIT NCPROGRAM ; APPEND TOOLPATH $tp   // добавить траекторию
    EDIT NCPROGRAM $имя FILENAME "путь"    // путь выходного файла
    EDIT NCPROGRAM $имя NUMBER 100         // номер программы
    EDIT NCPROGRAM $имя TAPEOPTIONS "…pmoptz"   // постпроцессор
    DEACTIVATE NCPROGRAM
    ACTIVATE NCPROGRAM $имя KEEP NCPROGRAM ;     // ВЫВОД файла

Честные оговорки, которые попадают в отчёт (и о них нельзя забывать):

* NC-файл **не проверяется на станке**; мы проверяем только то, что PowerMill
  создал программу, вложил в неё нужные траектории и записал файл;
* постпроцессор должен соответствовать станку — если он не задан, PowerMill
  возьмёт тот, что стоит в настройках проекта, и об этом будет сказано прямо;
* порядок траекторий в программе — тот, что указан в плане (технолог может
  поменять);
* мы не проверяем кадры NC-файла — для этого есть NCSIMUL (он у тебя есть) или
  симуляция самого PowerMill (пункт 35 — это проверки траекторий, не NC).

Если программы с таким именем в проекте уже есть — по умолчанию не перезаписываем,
а сообщаем: так случайно не потеряется ранее выведенная программа.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from config import DATA_ROOT, OUTPUT_DIR
from src import pml_files

MACRO_FILE = OUTPUT_DIR / "pm_nc.mac"
RESULT_FILE = OUTPUT_DIR / "pm_nc_result.txt"
STEP_MARK = "NC;"


@dataclass
class NcPlan:
    """Что выводим."""

    name: str = "PROGRAM"                      # имя NC-программы в проекте
    toolpaths: list[str] = field(default_factory=list)
    filename: Path | None = None               # путь выходного файла (.tap/.nc/.h)
    number: int = 100                          # номер программы
    postprocessor: Path | None = None          # .pmoptz (можно не задавать)
    overwrite: bool = False                    # перезаписать одноимённую программу
    result_file: Path = RESULT_FILE


def validate_plan(plan: NcPlan) -> list[str]:
    """Возможные возражения по плану (пусто — всё в порядке)."""
    problems: list[str] = []
    if not plan.toolpaths:
        problems.append("не выбрано ни одной траектории — программе нечего выводить")
    if not (plan.name or "").strip():
        problems.append("у программы пустое имя")
    if plan.number <= 0:
        problems.append("номер программы должен быть положительным")
    if plan.postprocessor is not None and not Path(plan.postprocessor).exists():
        problems.append(f"файла постпроцессора нет: {plan.postprocessor}")
    if plan.filename is not None and not Path(plan.filename).suffix:
        problems.append("у выходного файла нет расширения (например .tap или .nc)")
    return problems


def build_macro(plan: NcPlan, known_programs: list[str] | None = None) -> str:
    """Макрос вывода NC: создать программу, вложить траектории, записать файл.

    `known_programs` — программы, которые уже есть в проекте (их имена читает
    пункт 36 через COM). Если имя совпадает и перезапись не разрешена, макрос
    ничего не делает и честно об этом пишет.
    """
    known = [name for name in (known_programs or []) if name]
    out = str(plan.result_file).replace("\\", "/")
    when = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_name = plan.name.replace("'", "''")

    lines: list[str] = [
        "// ============================================================",
        "//  PowerMill AI — вывод NC-программы (шаг 3.5, пункт 36)",
        f"//  Собрано: {when}",
        "//  Создаёт NC-программу, вкладывает траектории и пишет файл.",
        "//  Команды — из рабочих макросов Autodesk «Macro to create NC code».",
        "// ============================================================",
        "",
        "RESET LOCALVARS",
        "",
        f"STRING $pm_res = '{out}'",
        'STRING $pm_tag = "PM_NC_RESULT"',
        "FILE OPEN $pm_res FOR WRITE AS ncout",
        "FILE WRITE $pm_tag TO ncout",
        "",
        f'STRING $pm_head = "PowerMill AI: вывод NC-программы {plan.name}"',
        "PRINT $pm_head",
        "FILE WRITE $pm_head TO ncout",
        "",
    ]

    # проверка: нет ли такой программы в проекте
    if known and not plan.overwrite:
        lines += [
            f"IF ENTITY_EXISTS('ncprogram', '{safe_name}') {{",
            f'    STRING $pm_dup = "{STEP_MARK}exists;fail;программа «{plan.name}» уже есть в проекте — включи перезапись (overwrite), если нужно заменить"',
            "    FILE WRITE $pm_dup TO ncout",
            "} ELSE {",
        ]
        inner = "    "
    else:
        inner = ""

    if plan.overwrite:
        lines.append(f"{inner}// перезапись разрешена: старую программу с таким именем удаляем")
        lines.append(f"{inner}IF ENTITY_EXISTS('ncprogram', '{safe_name}') {{")
        lines.append(f"{inner}    DELETE NCPROGRAM '{safe_name}'")
        lines.append(f"{inner}}}")

    lines += [
        f"{inner}CREATE NCPROGRAM '{safe_name}'",
        f'{inner}STRING $pm_created = "{STEP_MARK}create;ok;{plan.name}: программа создана"',
        f"{inner}FILE WRITE $pm_created TO ncout",
        f"{inner}ACTIVATE NCPROGRAM '{safe_name}'",
    ]

    for toolpath in plan.toolpaths:
        safe_tp = toolpath.replace("'", "''")
        lines += [
            f"    // траектория: {toolpath}",
            f"    IF ENTITY_EXISTS('toolpath', '{safe_tp}') {{",
            f"        EDIT NCPROGRAM ; APPEND TOOLPATH '{safe_tp}'",
            f'        STRING $pm_add = "{STEP_MARK}append;ok;{toolpath}"',
            "    } ELSE {",
            f'        STRING $pm_add = "{STEP_MARK}append;fail;{toolpath}: такой траектории в проекте нет"',
            "    }",
            "    FILE WRITE $pm_add TO ncout",
        ]

    if plan.filename is not None:
        target = str(plan.filename).replace("\\", "/")
        lines += [
            f"    // путь выходного файла",
            f"    EDIT NCPROGRAM '{safe_name}' FILENAME '{target}'",
            f'    STRING $pm_file = "{STEP_MARK}filename;ok;{target}"',
            "    FILE WRITE $pm_file TO ncout",
        ]

    if plan.postprocessor is not None:
        post = str(plan.postprocessor).replace("\\", "/")
        lines += [
            "    // постпроцессор (файл .pmoptz)",
            f"    EDIT NCPROGRAM '{safe_name}' TAPEOPTIONS '{post}'",
            f'    STRING $pm_post = "{STEP_MARK}postprocessor;ok;{post}"',
            "    FILE WRITE $pm_post TO ncout",
        ]

    lines += [
        f"    EDIT NCPROGRAM '{safe_name}' NUMBER {int(plan.number)}",
        f'    STRING $pm_num = "{STEP_MARK}number;ok;{int(plan.number)}"',
        "    FILE WRITE $pm_num TO ncout",
        "    DEACTIVATE NCPROGRAM",
        "",
        "    // ---- вывод файла: KEEP NCPROGRAM = записать NC ----",
        f"    ACTIVATE NCPROGRAM '{safe_name}' KEEP NCPROGRAM ;",
        f'    STRING $pm_out = "{STEP_MARK}write;ok;файл NC записан (смотри папку ncprograms проекта)"',
        "    FILE WRITE $pm_out TO ncout",
        "    DEACTIVATE NCPROGRAM",
    ]

    if known and not plan.overwrite:
        lines.append("}")

    lines += [
        "",
        'STRING $pm_done = "Вывод NC закончен. Отчёт: " + $pm_res',
        "FILE WRITE $pm_done TO ncout",
        "FILE CLOSE ncout",
        "PRINT $pm_done",
        "MESSAGE INFO $pm_done",
    ]
    return "\n".join(lines) + "\n"


def write_macro(plan: NcPlan, path: Path | str = MACRO_FILE,
                known_programs: list[str] | None = None) -> Path:
    """Пишет макрос вывода NC (CP1251, CRLF)."""
    target = Path(path)
    pml_files.write(target, build_macro(plan, known_programs=known_programs))
    return target


# --------------------------------------------------------------------------
# Разбор результата и честный итог
# --------------------------------------------------------------------------
def parse_result(text: str) -> list[tuple[str, str, str]]:
    """Строки отчёта макроса: [(шаг, статус, подробность)]."""
    found: list[tuple[str, str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line.startswith(STEP_MARK):
            continue
        parts = line[len(STEP_MARK):].split(";", 2)
        if len(parts) < 2:
            continue
        step, status = parts[0].strip(), parts[1].strip()
        detail = parts[2].strip() if len(parts) > 2 else ""
        found.append((step, status, detail))
    return found


STEP_TITLES = {
    "exists": "Проверка имени программы",
    "create": "Создание NC-программы",
    "append": "Траектории в программе",
    "filename": "Путь выходного файла",
    "postprocessor": "Постпроцессор",
    "number": "Номер программы",
    "write": "Запись файла NC",
}


def format_result(steps: list[tuple[str, str, str]]) -> str:
    """Полный отчёт по шагам."""
    if not steps:
        return ("  Данных от макроса пока нет: он либо ещё не запускался, либо "
                "не смог записать отчёт.")
    lines: list[str] = []
    for step, status, detail in steps:
        mark = {"fail": "✘", "skip": "•"}.get(status, "✔")
        lines.append(f"  {mark} {STEP_TITLES.get(step, step)}: {detail or status}")
    return "\n".join(lines)


def not_checked_lines(plan: NcPlan) -> list[str]:
    """Что в этой программе НЕ проверено — печатаем всегда, без исключений."""
    lines = [
        "Что НЕ проверено (честно):",
        "  • NC-файл не прогонялся на станке и не проверялся в NCSIMUL;",
        "  • кадры программы (G-код) мы не читаем и не сверяем с чертежом;",
    ]
    if plan.postprocessor is None:
        lines.append("  • постпроцессор не задавали — PowerMill взял тот, что стоит "
                     "в настройках проекта; проверь, что он от твоего станка;")
    else:
        lines.append(f"  • постпроцессор задан файлом {Path(plan.postprocessor).name}; "
                     "что он подходит станку — проверяет технолог;")
    lines.append("  • порядок траекторий в программе — как в плане, а не как "
                 "подсказывает симуляция;")
    return lines


def last_result(path: Path | str = RESULT_FILE) -> tuple[list[tuple[str, str, str]], str]:
    """Читает отчёт макроса: (шаги, пояснение)."""
    file = Path(path)
    if not file.exists():
        return [], f"файла ещё нет ({file})"
    steps = parse_result(pml_files.read(file))
    age = time.time() - file.stat().st_mtime
    if age > 3600:
        when = time.strftime("%d.%m %H:%M", time.localtime(file.stat().st_mtime))
        return steps, f"отчёт от {when} — если проект другой, запусти заново"
    return steps, ""


def default_filename(project_folder: Path | str | None, name: str,
                     suffix: str = ".tap") -> Path:
    """Куда писать NC: папка проекта (ncprograms) или наш output."""
    base = Path(project_folder) if project_folder else DATA_ROOT / "output" / "nc"
    return base / "ncprograms" / f"{name}{suffix}"


def find_postprocessors(extra_dirs: list[Path] | None = None,
                        limit: int = 30) -> list[Path]:
    """Ищет файлы постпроцессоров (.pmoptz) — чтобы предложить выбор в мастере."""
    roots: list[Path] = list(extra_dirs or [])
    for candidate in (
        DATA_ROOT / "post",
        DATA_ROOT / "output" / "post",
        Path("C:/Program Files/Autodesk/PowerMill 2026/lib/post"),
        Path("C:/Program Files/Autodesk/PowerMill 2026/file/post"),
    ):
        roots.append(candidate)
    # установки PowerMill на диске E (частый случай: E:\powermill 2026\…)
    for root in (Path("E:/"), Path("D:/")):
        if not root.exists():
            continue
        try:
            roots.extend(sorted(root.glob("powermill*/**/post"), reverse=True)[:3])
        except OSError:
            continue

    found: list[Path] = []
    for folder in roots:
        if not folder or not Path(folder).exists():
            continue
        try:
            for path in sorted(Path(folder).glob("*.pmoptz")):
                if path not in found:
                    found.append(path)
        except OSError:
            continue
        if len(found) >= limit:
            break
    return found[:limit]


def preview(plan: NcPlan) -> list[str]:
    """Что будет сделано — до выполнения."""
    lines = [
        f"  1. NC-программа «{plan.name}», номер {int(plan.number)}",
        f"  2. Траектории (по порядку): {', '.join(plan.toolpaths) or '— ни одной'}",
    ]
    if plan.filename is not None:
        lines.append(f"  3. Выходной файл: {plan.filename}")
    else:
        lines.append("  3. Путь файла: как в настройках проекта (папка ncprograms)")
    if plan.postprocessor is not None:
        lines.append(f"  4. Постпроцессор: {plan.postprocessor}")
    else:
        lines.append("  4. Постпроцессор: как в настройках проекта (не меняю)")
    lines.append("  5. Вывод файла командой ACTIVATE NCPROGRAM … KEEP NCPROGRAM ;")
    if plan.overwrite:
        lines.append("  6. Перезапись: одноимённая программа в проекте будет удалена")
    return lines

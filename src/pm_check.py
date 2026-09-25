"""
Проверки траекторий в живом PowerMill (шаг 3.4, пункт 35).

Что проверяем и почему именно так
---------------------------------
PowerMill умеет проверять траектории сам — командами `EDIT COLLISION`, которые
берутся из рабочего макроса с форума Autodesk (тема «Macro to simulate all
toolpaths in project»):

    EDIT COLLISION TYPE GOUGE              // зарезы (врезание в материал)
    EDIT COLLISION APPLY
    EDIT COLLISION TYPE COLLISION          // столкновения державки/хвостовика
    EDIT COLLISION SHANK_CLEARANCE "0.005"
    EDIT COLLISION HOLDER_CLEARANCE "0.075"
    EDIT COLLISION SPLIT_TOOLPATH Y
    EDIT COLLISION DEPTH Y
    EDIT COLLISION ADJUST_TOOL Y
    EDIT COLLISION APPLY

Результат PowerMill хранит в свойствах траектории, и оттуда его читаем:

    $tp.Computed                          — посчитана ли траектория
    $tp.Verification.GougeChecked         — проверялись ли зарезы
    $tp.Verification.CollisionChecked     — проверялись ли столкновения
    $tp.Safety.Tool.Cutting.Status        — статус безопасности при резании
                                            ("safe" / "collides" / …)

Мы не переизобретаем проверки и не делаем вид, что «посчитали сами»: запускаем
штатный механизм PowerMill и честно читаем его результат. Что прочитать не
удалось — так и пишем в отчёте (для этого у каждого рискованного шага свой
файл-отметка `pm_check_trace_*.txt`: по последней отметке видно, где макрос
остановился, как в самопроверке моста из пункта 28).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from config import OUTPUT_DIR
from src import pml_files

MACRO_FILE = OUTPUT_DIR / "pm_check.mac"
RESULT_FILE = OUTPUT_DIR / "pm_check_result.txt"


def trace_files() -> list[Path]:
    """Файлы-отметки: 1 — зарезы, 2 — коллизии, 3 — чтение статусов."""
    return [OUTPUT_DIR / f"pm_check_trace_{index}.txt" for index in (1, 2, 3)]


@dataclass
class CheckPlan:
    """Что проверяем."""

    toolpaths: list[str] = field(default_factory=list)
    gouge: bool = True                      # проверять зарезы
    collision: bool = True                  # проверять столкновения
    recalc: bool = True                     # досчитывать нерассчитанные
    holder_clearance: float = 0.1           # мм
    shank_clearance: float = 0.1            # мм
    read_status: bool = True                # читать Safety-статусы (рискованно)
    result_file: Path = RESULT_FILE


STEP_MARK = "CHK;"


def _num(value: float) -> str:
    return f"{value:g}"


def pml_path(path) -> str:
    """Путь в макросе — прямые слэши (так делает сама PowerMill)."""
    return str(path).replace("\\", "/")


def validate_plan(plan: CheckPlan) -> list[str]:
    """Понятные возражения по плану (пусто — всё в порядке)."""
    problems: list[str] = []
    if not plan.toolpaths:
        problems.append("не выбрано ни одной траектории — проверять нечего")
    for name in plan.toolpaths:
        if not name or name.strip() != name:
            problems.append(f"имя траектории с лишними пробелами: «{name}»")
    if plan.holder_clearance < 0 or plan.shank_clearance < 0:
        problems.append("зазоры не могут быть отрицательными")
    if not plan.gouge and not plan.collision and not plan.read_status:
        problems.append("все виды проверок выключены — смысла в запуске нет")
    return problems


def build_macro(plan: CheckPlan) -> str:
    """Макрос проверок: EDIT COLLISION + чтение статусов, с отметками шагов."""
    out = pml_path(plan.result_file)
    traces = [pml_path(path) for path in trace_files()]
    when = time.strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        "// ============================================================",
        "//  PowerMill AI — проверки траекторий (шаг 3.4, пункт 35)",
        f"//  Собрано: {when}",
        "//  Проверяет зарезы и столкновения штатными командами PowerMill",
        "//  (EDIT COLLISION), читает результат из свойств траектории.",
        "// ============================================================",
        "",
        "RESET LOCALVARS",
        "",
        f"STRING $pm_res = '{out}'",
        'STRING $pm_tag = "PM_CHECK_RESULT"',
        "FILE OPEN $pm_res FOR WRITE AS chkout",
        "FILE WRITE $pm_tag TO chkout",
        "",
    ]

    for index, name in enumerate(plan.toolpaths, 1):
        safe_name = name.replace("'", "''")
        # Объявляем переменные ЗАРАНЕЕ, на верхнем уровне макроса: внутри
        # IF/ELSE PowerMill разрешает только присваивание (иначе — «local
        # variable is already defined», на этом уже спотыкались).
        lines += [
            f'STRING $pm_missing_{index} = ""',
            f'STRING $pm_found_{index} = ""',
            f'STRING $pm_calc_{index} = ""',
            f'STRING $pm_gouge_{index} = ""',
            f'STRING $pm_coll_{index} = ""',
            f'STRING $pm_c_{index} = "no"',
            f'STRING $pm_cc_{index} = "no"',
            f'STRING $pm_gc_{index} = "no"',
            f'STRING $pm_vst_{index} = "skip"',
            f'STRING $pm_vdet_{index} = ""',
            f'STRING $pm_verify_{index} = ""',
            f'STRING $pm_status_{index} = ""',
            f'STRING $pm_safety_{index} = ""',
        ]
        if plan.gouge:
            lines += [
                f"STRING $pm_t1_{index} = '{traces[0]}'",
                f'STRING $pm_mark1_{index} = "шаг 1: проверяю зарезы"',
            ]
        if plan.collision:
            lines += [
                f"STRING $pm_t2_{index} = '{traces[1]}'",
                f'STRING $pm_mark2_{index} = "шаг 2: проверяю столкновения"',
            ]
        if plan.read_status:
            lines += [
                f"STRING $pm_t3_{index} = '{traces[2]}'",
                f'STRING $pm_mark3_{index} = "шаг 3: читаю статус безопасности"',
            ]
        lines += [
            f"// ---------- {name} ----------",
            f"IF NOT ENTITY_EXISTS('toolpath', '{safe_name}') {{",
            f'    $pm_missing_{index} = "{STEP_MARK}exists;fail;{name}: такой траектории в проекте нет"',
            f"    FILE WRITE $pm_missing_{index} TO chkout",
            "} ELSE {",
            f"    ENTITY $pm_tp_{index} = entity('toolpath', '{safe_name}')",
            f'    $pm_found_{index} = "{STEP_MARK}exists;ok;{name}"',
            f"    FILE WRITE $pm_found_{index} TO chkout",
        ]

        if plan.recalc:
            lines += [
                f"    IF NOT $pm_tp_{index}.Computed {{",
                f"        ACTIVATE TOOLPATH '{safe_name}'",
                f"        EDIT TOOLPATH '{safe_name}' CALCULATE",
                f'        $pm_calc_{index} = "{STEP_MARK}calculate;ok;{name}: траектория досчитана"',
                f"    }} ELSE {{",
                f'        $pm_calc_{index} = "{STEP_MARK}calculate;skip;{name}: уже посчитана"',
                "    }",
                f"    FILE WRITE $pm_calc_{index} TO chkout",
            ]

        lines += [
            f"    ACTIVATE TOOLPATH '{safe_name}'",
        ]

        if plan.gouge:
            lines += [
                "    // зарезы: отметка, чтобы знать, докуда дошёл макрос",
                f"    $pm_t1_{index} = '{traces[0]}'",
                f'    $pm_mark1_{index} = "шаг 1: проверяю зарезы"',
                f"    FILE OPEN $pm_t1_{index} FOR WRITE AS chk_a{index}",
                f"    FILE WRITE $pm_mark1_{index} TO chk_a{index}",
                f"    FILE CLOSE chk_a{index}",
                "    EDIT COLLISION TYPE GOUGE",
                "    EDIT COLLISION APPLY",
                f'    $pm_gouge_{index} = "{STEP_MARK}gouge;ok;{name}: зарезы проверены"',
                f"    FILE WRITE $pm_gouge_{index} TO chkout",
            ]
        else:
            lines.append(
                f'    $pm_gouge_{index} = "{STEP_MARK}gouge;skip;{name}: проверка зарезов выключена"')
            lines.append(f"    FILE WRITE $pm_gouge_{index} TO chkout")

        if plan.collision:
            lines += [
                f"    $pm_t2_{index} = '{traces[1]}'",
                f'    $pm_mark2_{index} = "шаг 2: проверяю столкновения"',
                f"    FILE OPEN $pm_t2_{index} FOR WRITE AS chk_b{index}",
                f"    FILE WRITE $pm_mark2_{index} TO chk_b{index}",
                f"    FILE CLOSE chk_b{index}",
                "    EDIT COLLISION TYPE COLLISION",
                f'    EDIT COLLISION SHANK_CLEARANCE "{_num(plan.shank_clearance)}"',
                f'    EDIT COLLISION HOLDER_CLEARANCE "{_num(plan.holder_clearance)}"',
                "    EDIT COLLISION SPLIT_TOOLPATH Y",
                "    EDIT COLLISION DEPTH Y",
                "    EDIT COLLISION ADJUST_TOOL Y",
                "    EDIT COLLISION APPLY",
                f'    $pm_coll_{index} = "{STEP_MARK}collision;ok;{name}: столкновения проверены"',
                f"    FILE WRITE $pm_coll_{index} TO chkout",
            ]
        else:
            lines.append(
                f'    $pm_coll_{index} = "{STEP_MARK}collision;skip;{name}: проверка столкновений выключена"')
            lines.append(f"    FILE WRITE $pm_coll_{index} TO chkout")

        # статусы: то, что PowerMill записал в свойства траектории
        lines += [
            f"    $pm_c_{index} = \"no\"",
            f"    IF $pm_tp_{index}.Computed {{ $pm_c_{index} = \"yes\" }}",
            f"    $pm_cc_{index} = \"no\"",
            f"    IF $pm_tp_{index}.Verification.CollisionChecked {{ $pm_cc_{index} = \"yes\" }}",
            f"    $pm_gc_{index} = \"no\"",
            f"    IF $pm_tp_{index}.Verification.GougeChecked {{ $pm_gc_{index} = \"yes\" }}",
            f'    $pm_vdet_{index} = "{name}: столкновения проверены=" + $pm_cc_{index} + ", зарезы проверены=" + $pm_gc_{index} + ", посчитана=" + $pm_c_{index}',
            f'    $pm_vst_{index} = "skip"',
            f'    IF $pm_cc_{index} == "yes" {{',
            f'        IF $pm_gc_{index} == "yes" {{ $pm_vst_{index} = "ok" }}',
            "    }",
            f'    $pm_verify_{index} = "{STEP_MARK}verify;" + $pm_vst_{index} + ";" + $pm_vdet_{index}',
            f"    FILE WRITE $pm_verify_{index} TO chkout",
        ]

        if plan.read_status:
            lines += [
                f"    $pm_t3_{index} = '{traces[2]}'",
                f'    $pm_mark3_{index} = "шаг 3: читаю статус безопасности"',
                f"    FILE OPEN $pm_t3_{index} FOR WRITE AS chk_c{index}",
                f"    FILE WRITE $pm_mark3_{index} TO chk_c{index}",
                f"    FILE CLOSE chk_c{index}",
                f"    $pm_status_{index} = $pm_tp_{index}.Safety.Tool.Cutting.Status",
                f'    $pm_safety_{index} = "{STEP_MARK}safety;" + $pm_status_{index} + ";{name}: статус при резании: " + $pm_status_{index}',
                f"    FILE WRITE $pm_safety_{index} TO chkout",
            ]

        lines.append("}")
        lines.append("")

    lines += [
        'STRING $pm_done = "Проверки закончены. Отчёт: " + $pm_res',
        "FILE WRITE $pm_done TO chkout",
        "FILE CLOSE chkout",
        "PRINT $pm_done",
        "MESSAGE INFO $pm_done",
    ]
    return "\n".join(lines) + "\n"


def write_macro(plan: CheckPlan, path: Path | str = MACRO_FILE) -> Path:
    """Пишет макрос проверок (CP1251, CRLF — как читает PowerMill)."""
    target = Path(path)
    pml_files.write(target, build_macro(plan))
    return target


# --------------------------------------------------------------------------
# Разбор результата и вывод
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
    "exists": "Траектория в проекте",
    "calculate": "Расчёт траектории",
    "gouge": "Проверка зарезов",
    "collision": "Проверка столкновений",
    "verify": "Что PowerMill отметил как проверенное",
    "safety": "Статус безопасности",
}

# Статус «не всё хорошо» в терминах PowerMill
BAD_STATUSES = ("collide", "collision", "gouge", "unsafe", "warning", "error")


def classify_safety(status: str) -> str:
    """Статус PowerMill -> 'ok' | 'bad' | 'unknown'."""
    text = (status or "").strip().lower()
    if not text:
        return "unknown"
    if any(word in text for word in BAD_STATUSES):
        return "bad"
    if text in ("safe", "ok", "fine", "clear", "none"):
        return "ok"
    return "unknown"


def summarize(steps: list[tuple[str, str, str]]) -> tuple[bool, list[str]]:
    """(всё ли хорошо, строки итога) — то, что технолог читает первым делом."""
    lines: list[str] = []
    problems: list[str] = []
    checked: list[str] = []
    not_checked: list[str] = []

    for step, status, detail in steps:
        if step == "exists":
            if status == "fail":
                problems.append(detail or "траектории нет в проекте")
            else:
                checked.append(f"траектория есть: {detail}")
        elif step == "calculate":
            if status == "skip":
                not_checked.append(f"расчёт не понадобился: {detail}")
            else:
                checked.append(detail or "траектория досчитана")
        elif step == "gouge":
            (not_checked if status == "skip" else checked).append(detail)
        elif step == "collision":
            (not_checked if status == "skip" else checked).append(detail)
        elif step == "verify":
            if "проверены=no" in detail:
                not_checked.append(detail)
            else:
                checked.append(detail)
        elif step == "safety":
            verdict = classify_safety(status)
            if verdict == "bad":
                problems.append(f"⚠ {detail}")
            elif verdict == "ok":
                checked.append(detail)
            else:
                not_checked.append(f"статус непонятен, проверь глазами: {detail}")

    if not steps:
        lines.append("  Отчёта проверок нет: макрос не запускался или не смог "
                     "записать файл.")
        return False, lines

    for line in checked:
        lines.append(f"  ✔ {line}")
    for line in not_checked:
        lines.append(f"  • {line}")
    for line in problems:
        lines.append(f"  ✘ {line}")

    lines.append("")
    if problems:
        lines.append("  ИТОГ: есть замечания — смотри строки с ✘. Это не «ошибка "
                     "ассистента», а то, что нашёл PowerMill: правь траекторию "
                     "или параметры, потом запусти проверки снова.")
    else:
        lines.append("  ИТОГ: замечаний от PowerMill нет.")
    if not_checked:
        lines.append("  Не проверено (честно): "
                     + "; ".join(item.split(":")[0] for item in not_checked))
    lines.append("  Проверка не заменяет пробный прогон на станке.")
    return not problems, lines


def format_result(steps: list[tuple[str, str, str]]) -> str:
    """Полный отчёт по шагам — для файла и пункта 29."""
    if not steps:
        return ("  Данных от макроса пока нет: он либо ещё не запускался, либо "
                "не смог записать отчёт.")
    lines: list[str] = []
    for step, status, detail in steps:
        title = STEP_TITLES.get(step, step)
        mark = {"fail": "✘", "skip": "•"}.get(status, "✔")
        lines.append(f"  {mark} {title}: {detail or status}")
    return "\n".join(lines)


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


def missing_traces() -> list[Path]:
    """Каких отметок нет — по ним видно, докуда дошёл макрос."""
    return [path for path in trace_files() if not path.exists()]


def preview(plan: CheckPlan) -> list[str]:
    """Что будет сделано — технолог видит ДО выполнения."""
    lines: list[str] = []
    lines.append(f"  1. Траектории: {', '.join(plan.toolpaths) or '— ни одной'}")
    if plan.recalc:
        lines.append("  2. Нерассчитанные траектории будут досчитаны "
                     "(EDIT TOOLPATH … CALCULATE)")
    if plan.gouge:
        lines.append("  3. Зарезы: EDIT COLLISION TYPE GOUGE → APPLY")
    if plan.collision:
        lines.append(f"  4. Столкновения: EDIT COLLISION TYPE COLLISION, "
                     f"зазор хвостовика {_num(plan.shank_clearance)} мм, "
                     f"державки {_num(plan.holder_clearance)} мм → APPLY")
    if plan.read_status:
        lines.append("  5. Прочитаю статус безопасности траектории "
                     "(Safety.Tool.Cutting.Status)")
    lines.append("  6. Отчёт: " + str(plan.result_file))
    return lines


def result_paths() -> dict[str, Path]:
    """Файлы, которые создаёт пункт 35 (для пункта 29 и веб-интерфейса)."""
    return {"macro": MACRO_FILE, "result": RESULT_FILE}

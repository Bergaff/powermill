"""
Черновая операция в PowerMill: инструмент → заготовка → траектория (шаги 3.2–3.3).

Зачем
-----
Считать режимы и «положить их в проект» некуда, пока в проекте нет ни
инструмента, ни траектории. Этот модуль создаёт минимальный рабочий набор:

1. **Инструмент** — если в проекте нет, создаём (D16 фреза), иначе активируем
   существующий.
2. **Заготовка (Block)** — сброс по модели, чтобы блок обнял деталь.
3. **Траектория из шаблона стратегии** — `Model-Area-Clearance.003.ptf`
   (это и есть «Offset Area Clearance» из наших расчётов).
4. **Параметры стратегии** — направление резания, допуск, припуск, шаг,
   заглубление, ограничение по Z.
5. **Режимы** — обороты и подачи из нашего калькулятора.
6. **Проверки** — включение проверки коллизий (инструмент/державка/хвостовик).
7. **Расчёт** — только по явному подтверждению (это самая долгая операция).

Откуда взяты команды (не выдуманы)
----------------------------------
Все строки — из рабочих макросов на форуме Autodesk:

* создание инструмента и его параметры («Need help altering my macro to create
  a tool from database»):

      EDIT TPPAGE TOOL
      CREATE TOOL ; DRILL
      EDIT TOOL ; DIAMETER $diameter
      EDIT TOOL ; NUMBER COMMANDFROMUI 1
      RENAME Tool ; $newTool

* траектория из шаблона и параметры стратегии («Macro not using input»,
  «Prompting questions in a macro»):

      IMPORT TEMPLATE ENTITY TOOLPATH TMPLTSELECTORGUI "3D-Area-Clearance/Model-Area-Clearance.003.ptf"
      EDIT TPPAGE SWBlock
      EDIT BLOCK COORDINATE WORLD
      EDIT BLOCK RESET
      EDIT BLOCK RESETLIMIT ".01"
      EDIT TPPAGE SWAreaClearance
      EDIT PAR 'CutDirection' 'any'
      EDIT PAR 'Tolerance' ".0002"
      EDIT PAR 'Thickness' "0.0"
      EDIT PAR 'Stepover' $stepover
      EDIT PAR 'AreaClearance.ZHeights.Stepdown' $stepdown
      EDIT TPPAGE SWToolRapidMv
      EDIT TOOLPATH SAFEAREA CALCULATE_DIMENSIONS
      EDIT TPPAGE SWLeadsLinks
      EDIT TOOLPATH LEADS LEADIN RAMP
      EDIT TPPAGE SWAutoVerifBasic
      EDIT PAR 'CollisionCheck' '1'
      EDIT TPPAGE SWFeedSpeed
      EDIT RPM $rpm
      EDIT FRATE $feed
      EDIT PRATE $plunge
      RENAME TOOLPATH "1" "DESBASTE"
      EDIT TOOLPATH "DESBASTE" CALCULATE

Что модуль делает честно
------------------------
* слова типа инструмента (`CREATE TOOL ; END_MILL`) не подтверждены — поэтому
  макрос пробует варианты и **пишет в отчёт**, какой сработал;
* после каждого шага в файл результата идёт строка `STEP;<шаг>;<ok|fail>;<что>`,
  по ней видно, где именно споткнулись;
* расчёт траектории включается только если пользователь согласился.
"""
from __future__ import annotations

from src import pml_files

import time
from dataclasses import dataclass
from pathlib import Path

from config import OUTPUT_DIR

MACRO_FILE = OUTPUT_DIR / "pm_operation.mac"
RESULT_FILE = OUTPUT_DIR / "pm_operation_result.txt"

# Шаблон стратегии «Offset Area Clearance» (он же Model Area Clearance)
DEFAULT_TEMPLATE = "3D-Area-Clearance/Model-Area-Clearance.003.ptf"

# Варианты слова для создания фрезы: подтверждён только DRILL (форум Autodesk),
# поэтому перебираем и проверяем результат по числу инструментов в проекте.
END_MILL_WORDS: tuple[str, ...] = ("END_MILL", "ENDMILL", "END MILL")


def tool_words() -> list[str]:
    """Слова для `CREATE TOOL`, начиная с того, что уже сработало (пункт 33).

    Порядок важен: макрос останавливается на первой неверной команде, поэтому
    сначала подставляем проверенное на твоём PowerMill слово (его записал
    пункт 33 в output\\pm_tool_word.txt), а потом уже варианты из справки.
    """
    from src.pm_tool import word_order

    return word_order(END_MILL_WORDS)

STEP_MARK = "STEP;"


@dataclass
class OperationPlan:
    """Что именно собрать в проекте."""

    toolpath_name: str
    tool_name: str
    tool_diameter: float = 16.0
    tool_number: int = 1
    create_tool: bool = True
    template: str = DEFAULT_TEMPLATE
    cut_direction: str = "any"
    tolerance: float = 0.05
    thickness: float = 0.0            # припуск: 0 — черновая «в размер»
    stepover: float | None = None     # ae, мм
    stepdown: float | None = None     # ap, мм
    z_min: float | None = None        # ограничение снизу, мм (None — как в шаблоне)
    rpm: int | None = None
    feed: int | None = None
    plunge: int | None = None
    block_z_max: float | None = None  # верх заготовки, мм (None — по модели)
    calculate: bool = False           # расчёт — только по подтверждению


def _num(value: float) -> str:
    return f"{value:g}"


def build_macro(plan: OperationPlan, result_file: Path | str = RESULT_FILE,
                stamp: str | None = None) -> str:
    """Текст PML-макроса, который собирает операцию и пишет отчёт о шагах."""
    out_file = str(result_file).replace("\\", "/")
    when = stamp or time.strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        "// ============================================================",
        "//  PowerMill AI — черновая операция (шаги 3.2–3.3)",
        f"//  Собрано: {when}",
        "//  Меняет проект: создаёт инструмент (если нет), сбрасывает заготовку,",
        "//  создаёт траекторию из шаблона и выставляет параметры и режимы.",
        "//  Запускать на КОПИИ проекта и после подтверждения.",
        "// ============================================================",
        "",
        "RESET LOCALVARS",
        "",
        f"STRING $pm_res = '{out_file}'",
        "FILE OPEN $pm_res FOR WRITE AS out",
        'STRING $pm_tag = "PM_OPERATION_RESULT"',
        "FILE WRITE $pm_tag TO out",
        "",
        'STRING $pm_head = "PowerMill AI: собираю операцию " + "'
        + plan.toolpath_name + '"',
        "PRINT $pm_head",
        "",
        "// ---------- 1. Инструмент ----------",
        "EDIT TPPAGE TOOL",
    ]

    if plan.create_tool:
        lines += [
            f"INT $pm_tools0 = SIZE(folder('Tool'))",
            f'STRING $pm_step1 = "{STEP_MARK}tool;start;было инструментов: " + STRING($pm_tools0)',
            "FILE WRITE $pm_step1 TO out",
            "PRINT $pm_step1",
        ]
        for index, word in enumerate(tool_words()):
            lines += [
                f"IF SIZE(folder('Tool')) == $pm_tools0 {{",
                f"    CREATE TOOL ; {word}",
                f"    STRING $pm_try{index} = \"{STEP_MARK}tool_create;try;{word};\" + "
                "STRING(SIZE(folder('Tool')))",
                f"    FILE WRITE $pm_try{index} TO out",
                f"    PRINT $pm_try{index}",
                "}",
            ]
        lines += [
            "INT $pm_tools1 = SIZE(folder('Tool'))",
            f'STRING $pm_step2 = "{STEP_MARK}tool_create;" + '
            'STRING($pm_tools1 != $pm_tools0) + ";" + STRING($pm_tools1)',
            "FILE WRITE $pm_step2 TO out",
            "PRINT $pm_step2",
            "IF $pm_tools1 == $pm_tools0 {",
            f'    STRING $pm_fail = "{STEP_MARK}tool_create;fail;ни одно слово не подошло"',
            "    FILE WRITE $pm_fail TO out",
            "    PRINT $pm_fail",
            "} ELSE {",
            f"    EDIT TOOL ; DIAMETER {_num(plan.tool_diameter)}",
            f"    EDIT TOOL ; NUMBER COMMANDFROMUI {plan.tool_number}",
            f"    RENAME Tool ; '{plan.tool_name}'",
            f'    STRING $pm_tool_name = "{STEP_MARK}tool_name;" + $Tool.Name + ";" + '
            "STRING($Tool.Diameter)",
            "    FILE WRITE $pm_tool_name TO out",
            "    PRINT $pm_tool_name",
            "}",
        ]
    else:
        lines += [
            f"ACTIVATE TOOL '{plan.tool_name}'",
            f'STRING $pm_tool_act = "{STEP_MARK}tool_active;" + $Tool.Name + ";" + '
            "STRING($Tool.Diameter)",
            "FILE WRITE $pm_tool_act TO out",
            "PRINT $pm_tool_act",
        ]

    lines += [
        "",
        "// ---------- 2. Заготовка (Block) по модели ----------",
        "EDIT TPPAGE SWBlock",
        "EDIT BLOCK COORDINATE WORLD",
        "EDIT BLOCK RESET",
        f'EDIT BLOCK RESETLIMIT "{_num(plan.tolerance)}"',
    ]
    if plan.block_z_max is not None:
        lines.append(f'EDIT BLOCK ZMAX "{_num(plan.block_z_max)}"')
    lines += [
        f'STRING $pm_block = "{STEP_MARK}block;ok;" + STRING($Block.XLength) + ";" + '
        "STRING($Block.YLength) + \";\" + STRING($Block.ZLength)",
        "FILE WRITE $pm_block TO out",
        "PRINT $pm_block",
        "",
        "// ---------- 3. Траектория из шаблона стратегии ----------",
        "INT $pm_tp_before = SIZE(folder('Toolpath'))",
        f'IMPORT TEMPLATE ENTITY TOOLPATH TMPLTSELECTORGUI "{plan.template}"',
        "INT $pm_tp_after = SIZE(folder('Toolpath'))",
        f'STRING $pm_tp_new = "{STEP_MARK}toolpath;" + STRING($pm_tp_after) + ";" + '
        'STRING($pm_tp_after != $pm_tp_before)',
        "FILE WRITE $pm_tp_new TO out",
        "PRINT $pm_tp_new",
        "",
        "// ---------- 4. Параметры стратегии ----------",
        "EDIT TPPAGE SWAreaClearance",
        f"EDIT PAR 'CutDirection' '{plan.cut_direction}'",
        f'EDIT PAR \'Tolerance\' "{_num(plan.tolerance)}"',
        f'EDIT PAR \'Thickness\' "{_num(plan.thickness)}"',
    ]
    if plan.stepover is not None:
        lines.append(f"EDIT PAR 'Stepover' {_num(plan.stepover)}")
    if plan.stepdown is not None:
        lines.append(f"EDIT PAR 'AreaClearance.ZHeights.Stepdown' {_num(plan.stepdown)}")
    lines += [
        "EDIT TPPAGE SWLimit",
        f'EDIT PAR \'ZRange.Minimum.Active\' {"1" if plan.z_min is not None else "0"}',
    ]
    if plan.z_min is not None:
        lines.append(f"EDIT PAR 'ZRange.Minimum.Value' {_num(plan.z_min)}")
    lines += [
        "EDIT TPPAGE SWToolRapidMv",
        "EDIT TOOLPATH SAFEAREA CALCULATE_DIMENSIONS",
        "EDIT TPPAGE SWLeadsLinks",
        "EDIT TOOLPATH LEADS LEADIN RAMP",
        "EDIT TPPAGE SWAutoVerifBasic",
        "EDIT PAR 'CollisionCheck' '1'",
        'EDIT PAR \'Clearance.Holder\' "0.1"',
        'EDIT PAR \'Clearance.Shank\' "0.1"',
        f'STRING $pm_params = "{STEP_MARK}params;ok;готово"',
        "FILE WRITE $pm_params TO out",
        "PRINT $pm_params",
    ]

    if plan.rpm or plan.feed or plan.plunge:
        lines += [
            "",
            "// ---------- 5. Режимы резания ----------",
            "EDIT TPPAGE SWFeedSpeed",
        ]
        if plan.rpm:
            lines.append(f'EDIT RPM "{plan.rpm}"')
        if plan.feed:
            lines.append(f'EDIT FRATE "{plan.feed}"')
        if plan.plunge:
            lines.append(f'EDIT PRATE "{plan.plunge}"')
        lines += [
            f'STRING $pm_feed = "{STEP_MARK}feeds;ok;" + '
            'STRING($toolpath.SpindleSpeed.Value) + ";" + '
            'STRING($toolpath.Feedrate.Cutting.Value)',
            "FILE WRITE $pm_feed TO out",
            "PRINT $pm_feed",
        ]

    lines += [
        "",
        "// ---------- 6. Имя траектории и (по желанию) расчёт ----------",
        f"RENAME TOOLPATH ; '{plan.toolpath_name}'",
        f'STRING $pm_name = "{STEP_MARK}rename;ok;{plan.toolpath_name}"',
        "FILE WRITE $pm_name TO out",
        "PRINT $pm_name",
    ]
    if plan.calculate:
        lines += [
            f'EDIT TOOLPATH "{plan.toolpath_name}" CALCULATE',
            f'STRING $pm_calc = "{STEP_MARK}calculate;ok;{plan.toolpath_name}"',
            "FILE WRITE $pm_calc TO out",
            "PRINT $pm_calc",
        ]
    else:
        lines += [
            f'STRING $pm_calc = "{STEP_MARK}calculate;skip;ты не подтверждал расчёт"',
            "FILE WRITE $pm_calc TO out",
            "PRINT $pm_calc",
        ]

    lines += [
        "",
        "FILE CLOSE out",
        f'STRING $pm_done = "PowerMill AI: операция "{plan.toolpath_name}'
        '" собрана. Отчёт: " + $pm_res',
        "PRINT $pm_done",
        "MESSAGE INFO $pm_done",
        "",
    ]
    return "\n".join(lines)


def preview(plan: OperationPlan) -> list[str]:
    """Что будет сделано — человеческим текстом, до запуска."""
    lines = ["  1. Инструмент:"]
    if plan.create_tool:
        lines.append(f"     создать фрезу D{_num(plan.tool_diameter)} "
                     f"(номер {plan.tool_number}), имя «{plan.tool_name}»")
        lines.append("     слова перебираются: " + ", ".join(tool_words())
                     + " — сработавший попадёт в отчёт")
    else:
        lines.append(f"     взять из проекта: «{plan.tool_name}»")
    lines.append(f"  2. Заготовка: сброс блока по модели "
                 f"(припуск {_num(plan.thickness)}, допуск {_num(plan.tolerance)})")
    lines.append(f"  3. Траектория из шаблона: {plan.template}")
    lines.append(f"  4. Параметры: направление '{plan.cut_direction}', "
                 f"допуск {_num(plan.tolerance)}, припуск {_num(plan.thickness)}"
                 + (f", шаг по XY {_num(plan.stepover)}" if plan.stepover else "")
                 + (f", заглубление {_num(plan.stepdown)}" if plan.stepdown else ""))
    if plan.rpm or plan.feed:
        lines.append(f"  5. Режимы: S={plan.rpm or '—'}, F={plan.feed or '—'}, "
                     f"врезание={plan.plunge or '—'}")
    lines.append(f"  6. Имя траектории: «{plan.toolpath_name}», "
                 + ("расчёт ВКЛЮЧЁН" if plan.calculate else "без расчёта"))
    return lines


def write_macro(plan: OperationPlan, path: Path | str = MACRO_FILE,
                result_file: Path | str = RESULT_FILE) -> Path:
    """Пишет макрос (windows-переводы строк, как у макросов PowerMill)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pml_files.write(target, build_macro(plan, result_file=result_file))
    return target


# --------------------------------------------------------------------------
# Разбор отчёта макроса
# --------------------------------------------------------------------------
def parse_result(text: str) -> list[tuple[str, str, str]]:
    """Строки отчёта макроса: [(шаг, статус, подробность)]."""
    found: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith(STEP_MARK):
            continue
        parts = line[len(STEP_MARK):].split(";")
        if len(parts) < 2:
            continue
        step, status = parts[0].strip(), parts[1].strip()
        detail = ";".join(part.strip() for part in parts[2:])
        found.append((step, status, detail))
    return found


STEP_TITLES = {
    "tool": "Инструмент",
    "tool_create": "Создание инструмента",
    "tool_name": "Параметры инструмента",
    "tool_active": "Выбор инструмента из проекта",
    "block": "Заготовка (Block)",
    "toolpath": "Траектория из шаблона",
    "params": "Параметры стратегии",
    "feeds": "Режимы резания",
    "rename": "Имя траектории",
    "calculate": "Расчёт траектории",
}

# Что не «ok», а честное «пропущено»
SKIP_STATUSES = {"skip"}


def format_result(steps: list[tuple[str, str, str]]) -> str:
    """Читаемый итог: что получилось, что нет."""
    if not steps:
        return ("  Данных от макроса пока нет: он либо ещё не запускался, либо "
                "не смог записать отчёт.")
    lines: list[str] = []
    for step, status, detail in steps:
        title = STEP_TITLES.get(step, step)
        if status == "fail":
            mark = "✘"
        elif status in SKIP_STATUSES:
            mark = "•"
        elif status == "try":
            mark = "…"
        else:
            mark = "✔"
        lines.append(f"  {mark} {title}: {detail or status}")
    bad = [step for step, status, _ in steps if status == "fail"]
    if bad:
        lines.append("")
        lines.append("  Что делать: пришли этот отчёт — по этим строкам видно, "
                     "на каком месте PowerMill не принял команду, и мы подберём "
                     "точный вариант для твоей версии.")
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
    return steps, "свежий отчёт"

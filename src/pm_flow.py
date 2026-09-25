"""
Шаг 3.6 — «сказал: делай».

Что делает этот модуль
----------------------
Собирает ОДИН план из того, что уже проверено вживую:

1. фреза (создать или взять из проекта)          — шаг 3.2 / пункт 33
2. заготовка (Block) по модели                    — шаг 3.2
3. траектория из шаблона стратегии + параметры     — шаг 3.3
4. режимы резания (S, F, врезание)                 — шаг 3.1
5. расчёт (по желанию)                             — шаг 3.3
6. проверки зарезов и столкновений                 — шаг 3.4 / пункт 35
7. вывод NC-программы (по желанию)                 — шаг 3.5 / пункт 36

Порядок и правила, которые модуль соблюдает:

* **план показывается до выполнения** — списком, с числами (диаметр, шаг,
  заглубление, S/F, лимиты по Z), а не «потом посмотришь»;
* проект меняется только после подтверждения; сначала макрос печатается/пишется
  на диск, потом запускается;
* проверки и NC — отдельные шаги после расчёта, и в итоговом отчёте видно, что
  проверено, а что нет (проверки читают статус из PowerMill, NC — честно
  помечается как «на станке не проверялось»);
* если чего-то не хватает (нет модели, нет расчёта, нет траектории) — модуль
  говорит прямо и останавливается на этом шаге, а не делает вид, что всё прошло.

Модуль ничего не знает про консоль: он строит план, собирает макросы и читает
их отчёты. Показ и вопросы — в scripts\\make_flow.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from config import OUTPUT_DIR
from src import pm_check, pm_edit, pm_nc, pm_operation

REPORT_FILE = OUTPUT_DIR / "pm_flow_report.txt"
FLOW_MACRO = OUTPUT_DIR / "pm_flow.mac"

# Что делаем в потоке по умолчанию
DEFAULT_ALIASES = ("Chernovaya",)


@dataclass
class FlowRequest:
    """Что просит технолог (то, чего ассистент не может знать сам)."""

    material: str = "Сталь 40Х"                 # материал (по нему считаем режимы)
    tool_name: str = "D16_Freza"                # имя фрезы в проекте
    tool_diameter: float = 16.0                 # диаметр, мм
    tool_from_project: bool = False             # взять готовую фрезу, не создавать
    stock_margin_xy: float = 2.0                # припуск на заготовку по бокам, мм
    stock_margin_z: float = 0.0                 # припуск снизу, мм
    allowance: float = 0.0                      # припуск на чистовую (Thickness)
    stepover: float | None = None               # ae, мм (None — из расчёта)
    stepdown: float | None = None               # ap, мм (None — из расчёта)
    z_min: float | None = None                  # ограничение снизу, мм
    toolpath_name: str = "Chernovaya_D16"
    calculate: bool = True                      # считать траекторию
    check_after: bool = True                    # проверки после расчёта (3.4)
    nc_after: bool = False                      # вывод NC (3.5)
    nc_name: str = "PROGRAM1"
    nc_number: int = 100
    postprocessor: Path | None = None
    project_folder: Path | None = None          # папка проекта (для копии и NC)


@dataclass
class FlowReport:
    """Итог потока: что сделано, что проверено, что осталось за технологом."""

    request: FlowRequest | None = None
    steps: list[tuple[str, str, str]] = field(default_factory=list)   # (шаг, статус, текст)
    check_steps: list[tuple[str, str, str]] = field(default_factory=list)
    nc_steps: list[tuple[str, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    finished: bool = False

    def add(self, step: str, status: str, text: str = "") -> None:
        self.steps.append((step, status, text))

    # ---------------- отчёт ----------------
    def format(self) -> str:
        lines = [
            "PowerMill AI — поток «сказал: делай» (шаг 3.6)",
            time.strftime("Собрано: %d.%m.%Y %H:%M"),
            "",
        ]
        if self.request:
            lines += [
                "Задача:",
                f"  материал: {self.request.material}",
                f"  фреза: {self.request.tool_name} D{self.request.tool_diameter:g}"
                + (" (из проекта)" if self.request.tool_from_project else " (создать)"),
                f"  заготовка: модель + {self.request.stock_margin_xy:g} мм по бокам, "
                f"{self.request.stock_margin_z:g} мм снизу",
                f"  припуск на чистовую: {self.request.allowance:g} мм",
                f"  траектория: {self.request.toolpath_name}"
                + (", расчёт включён" if self.request.calculate else ", без расчёта"),
                "",
            ]
        lines.append("Что сделано:")
        for step, status, text in self.steps:
            mark = {"fail": "✘", "skip": "•"}.get(status, "✔")
            lines.append(f"  {mark} {step}: {text or status}")
        if self.check_steps:
            lines.append("")
            lines.append("Проверки после расчёта (пункт 35):")
            lines.extend("  " + line.strip() for line in
                         pm_check.summarize(self.check_steps)[1])
        if self.nc_steps:
            lines.append("")
            lines.append("NC-программа (пункт 36):")
            lines.extend("  " + line.strip()
                         for line in pm_nc.format_result(self.nc_steps).splitlines())
            lines.extend(pm_nc.not_checked_lines(pm_nc.NcPlan(
                name=self.request.nc_name if self.request else "PROGRAM",
                toolpaths=[self.request.toolpath_name] if self.request else [],
                postprocessor=self.request.postprocessor if self.request else None)))
        lines.append("")
        lines.append("Итог: " + ("поток доведён до конца"
                                 if self.finished else "поток остановлен — см. ✘ выше"))
        if self.warnings:
            lines.append("")
            lines.append("На что посмотреть:")
            lines.extend(f"  • {item}" for item in self.warnings)
        lines.append("")
        lines.append("Напоминание: ассистент не проверяет допуски по чертежу и не "
                     "заменяет пробный прогон на станке.")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# План (то, что видит технолог до выполнения)
# --------------------------------------------------------------------------
def build_plan(request: FlowRequest) -> tuple[pm_operation.OperationPlan, list[str]]:
    """План операции для PowerMill + человеческий список шагов.

    Режимы резания считаются тем же калькулятором, что и в пункте 3 меню
    (формулы, без ИИ), поэтому цифры всегда есть.
    """
    from src import cutting

    query = (f"{request.material}, фреза D{request.tool_diameter:g} z4, черновая")
    report, data = cutting.answer(query)

    stepover = request.stepover if request.stepover is not None else data.get("ae")
    stepdown = request.stepdown if request.stepdown is not None else data.get("ap")

    plan = pm_operation.OperationPlan(
        toolpath_name=request.toolpath_name or "Chernovaya_D16",
        tool_name=request.tool_name or "D16_Freza",
        tool_diameter=request.tool_diameter,
        create_tool=not request.tool_from_project,
        stepover=float(stepover) if stepover else None,
        stepdown=float(stepdown) if stepdown else None,
        z_min=request.z_min,
        thickness=request.allowance,
        rpm=int(data.get("S_rpm") or 0) or None,
        feed=int(data.get("F_mm_min") or 0) or None,
        plunge=int((data.get("F_mm_min") or 0) * 0.6) or None,
        tolerance=0.05,
        calculate=bool(request.calculate),
    )

    lines = [
        f"  1. Фреза: {plan.tool_name} D{plan.tool_diameter:g}"
        + (" — берём из проекта" if request.tool_from_project else " — создаём"),
        f"  2. Заготовка: по модели, припуск по бокам {request.stock_margin_xy:g} мм, "
        f"снизу {request.stock_margin_z:g} мм",
        f"  3. Траектория из шаблона Model-Area-Clearance (Offset Area Clearance), "
        f"имя «{plan.toolpath_name}»",
        f"  4. Параметры: шаг по XY {plan.stepover or '—'} мм, "
        f"заглубление {plan.stepdown or '—'} мм, допуск {plan.tolerance:g} мм, "
        f"припуск {plan.thickness:g} мм",
        f"  5. Режимы: S={plan.rpm or '—'} об/мин, F={plan.feed or '—'} мм/мин, "
        f"врезание {plan.plunge or '—'} мм/мин",
        "  6. " + ("Расчёт траектории — да" if plan.calculate else "Без расчёта"),
    ]
    if request.check_after:
        lines.append("  7. Проверки: зарезы и столкновения (пункт 35)")
    if request.nc_after:
        lines.append(f"  8. NC-программа «{request.nc_name}», номер {request.nc_number}")
    lines.append("")
    lines.append("  Режимы посчитаны формулами калькулятора (пункт 3 меню):")
    lines.extend("    " + line for line in report.splitlines()[:6])
    if not data.get("material"):
        lines.append("  (!) материал не распознан — считали по значению по умолчанию")
    return plan, lines


def warnings_for(request: FlowRequest) -> list[str]:
    """О чём обязательно предупредить технолога до запуска."""
    items: list[str] = []
    if request.allowance <= 0:
        items.append("припуск на чистовую 0 мм: траектория пойдёт «в размер» — "
                     "проверь, что это черновая, а не чистовая")
    if request.stock_margin_xy < 0 or request.stock_margin_z < 0:
        items.append("припуск на заготовку отрицательный — это уменьшит заготовку")
    if request.tool_diameter > 0 and request.stepover and \
            request.stepover > request.tool_diameter:
        items.append(f"шаг по XY {request.stepover:g} мм больше диаметра фрезы "
                     f"D{request.tool_diameter:g} — PowerMill оставит гребешки")
    if not request.calculate:
        items.append("расчёт выключен: траектория создастся, но не посчитается, "
                     "и проверки/NС будут неполными")
    if request.check_after and not request.calculate:
        items.append("проверки без расчёта не имеют смысла — включи расчёт")
    return items


def report_path() -> Path:
    return REPORT_FILE


def save_report(report: FlowReport) -> Path:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(report.format(), encoding="utf-8")
    return REPORT_FILE


# --------------------------------------------------------------------------
# Выполнение (шаги выполняет сценарий, модуль собирает и разбирает)
# --------------------------------------------------------------------------
def operation_macro(plan: pm_operation.OperationPlan) -> Path:
    """Пишет макрос операции (шаги 3.1–3.3) — его запускает PowerMill."""
    return pm_operation.write_macro(plan, path=FLOW_MACRO)


def backup(project_folder: Path | str | None) -> Path | None:
    """Копия проекта перед изменениями (как в пунктах 30/31)."""
    if not project_folder:
        return None
    try:
        return pm_edit.backup_project(project_folder)
    except OSError:
        return None


def summarize_operation(steps: list[tuple[str, str, str]]) -> list[str]:
    """Итог по шагам макроса операции — то же, что в пункте 31."""
    lines = pm_operation.format_result(steps).splitlines()
    return lines

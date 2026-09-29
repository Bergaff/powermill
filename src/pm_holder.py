"""
Хвостовик и патрон (державка) фрезы — чтобы проверка столкновений работала.

Зачем это появилось
-------------------
На живом PowerMill 2026 пункт 35 остановился на строке `EDIT COLLISION APPLY` с
ответом: **«не заданы ни хвостовик ни патрон»**. Проверка столкновений в PowerMill
считает не только режущую часть: ей нужны хвостовик и патрон (державка) у фрезы.
Пункты 33 и 37 создавали фрезу без них — значит, столкновения проверять было
нечем, и PowerMill честно это и сказал.

Что здесь есть
--------------
`HolderSpec` — условные размеры: цилиндр-хвостовик и цилиндр-патрон. Команды
взяты из рабочего макроса Autodesk (тема «Holder connection», форум 6706341):

    EDIT TOOL $tool SHANK_CLEAR
    EDIT TOOL $tool SHANK_COMPONENT ADD
    EDIT TOOL $tool SHANK_COMPONENT UPPERDIA $tool.diameter
    EDIT TOOL $tool SHANK_COMPONENT LOWERDIA $tool.diameter
    EDIT TOOL $tool HOLDER_CLEAR
    EDIT TOOL $tool HOLDER_COMPONENT ADD
    EDIT TOOL $tool HOLDER_COMPONENT UPPERDIA 10
    EDIT TOOL $tool HOLDER_COMPONENT LOWERDIA 10
    EDIT TOOL $tool HOLDER_COMPONENT LENGTH 20

Честная оговорка (она попадает в отчёты)
---------------------------------------
Это **условная** державка: два цилиндра, а не твоя реальная оснастка. Она годится,
чтобы PowerMill смог проверить столкновения и чтобы грубые случаи («патрон лезет в
заготовку») стали видны. Она НЕ заменяет настоящую державку из базы инструментов:
поставь свою в PowerMill (вкладка инструмента -> Holder) и повтори проверку —
тогда результат будет по делу.

Хвостовик/патрон задаются командами `*_CLEAR` — то есть **заменяют** то, что у
фрезы уже было. Поэтому спрашиваем разрешение до, а не делаем молча.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import DATA_ROOT

# Файл с размерами (вне Git): задал один раз — дальше берём оттуда.
SPEC_FILE = DATA_ROOT / "holder_defaults.json"


@dataclass
class HolderSpec:
    """Размеры условной державки, мм."""

    shank_diameter: float = 16.0        # диаметр хвостовика
    shank_length: float = 50.0          # длина хвостовика (от режущей части вверх)
    holder_lower_diameter: float = 40.0  # низ патрона (ближе к фрезе)
    holder_upper_diameter: float = 63.0  # верх патрона
    holder_length: float = 50.0          # длина патрона

    @classmethod
    def for_tool(cls, diameter: float) -> "HolderSpec":
        """Разумные умолчания по диаметру фрезы.

        Хвостовик — как фреза (так у цельных фрез и бывает), патрон — как
        типовой цанговый патрон под BT40/ER32: низ Ø40, корпус Ø63.
        """
        dia = float(diameter) if diameter and diameter > 0 else 16.0
        return cls(
            shank_diameter=round(dia, 3),
            shank_length=round(max(50.0, 3.0 * dia), 1),
            holder_lower_diameter=round(max(40.0, 2.5 * dia), 1),
            holder_upper_diameter=round(max(63.0, 4.0 * dia), 1),
            holder_length=50.0,
        )

    # --- текст ------------------------------------------------------------
    def describe(self) -> str:
        return (f"хвостовик Ø{self.shank_diameter:g}×{self.shank_length:g}, "
                f"патрон Ø{self.holder_lower_diameter:g}/"
                f"{self.holder_upper_diameter:g}×{self.holder_length:g}")

    def describe_ascii(self) -> str:
        """То же без Ø и ×: макросы PowerMill — CP1251, таких символов там нет."""
        return (f"хвостовик D{self.shank_diameter:g}x{self.shank_length:g}, "
                f"патрон D{self.holder_lower_diameter:g}/"
                f"{self.holder_upper_diameter:g}x{self.holder_length:g}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HolderSpec":
        known = {key: float(data[key]) for key in cls.__dataclass_fields__  # type: ignore[attr-defined]
                 if key in data and data[key] not in (None, "")}
        return cls(**known)

    # --- команды ----------------------------------------------------------
    def lines(self, tool: str, quote: bool = True) -> list[str]:
        """Строки PML: чистка и два цилиндра (подтверждено на форуме Autodesk).

        `quote=False` — когда вместо имени подставляется переменная PowerMill
        (`$Tool`): в макросе это надёжнее, чем литеральное имя.
        """
        safe = (tool or "").replace("'", "''")
        if not quote:
            return [line.replace(f"'{safe}'", tool) for line in self._lines(safe)]
        return self._lines(safe)

    def _lines(self, safe: str) -> list[str]:
        g = lambda value: f"{value:g}"  # noqa: E731
        return [
            f"EDIT TOOL '{safe}' SHANK_CLEAR",
            f"EDIT TOOL '{safe}' SHANK_COMPONENT ADD",
            f"EDIT TOOL '{safe}' SHANK_COMPONENT LOWERDIA {g(self.shank_diameter)}",
            f"EDIT TOOL '{safe}' SHANK_COMPONENT UPPERDIA {g(self.shank_diameter)}",
            f"EDIT TOOL '{safe}' SHANK_COMPONENT LENGTH {g(self.shank_length)}",
            f"EDIT TOOL '{safe}' HOLDER_CLEAR",
            f"EDIT TOOL '{safe}' HOLDER_COMPONENT ADD",
            f"EDIT TOOL '{safe}' HOLDER_COMPONENT LOWERDIA {g(self.holder_lower_diameter)}",
            f"EDIT TOOL '{safe}' HOLDER_COMPONENT UPPERDIA {g(self.holder_upper_diameter)}",
            f"EDIT TOOL '{safe}' HOLDER_COMPONENT LENGTH {g(self.holder_length)}",
        ]


def load_saved() -> HolderSpec | None:
    """Сохранённые размеры (или None, если их ещё не задавали)."""
    if not SPEC_FILE.exists():
        return None
    try:
        data = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return HolderSpec.from_dict(data)
    except (TypeError, ValueError):
        return None


def save_spec(spec: HolderSpec) -> Path:
    """Запоминает размеры — следующий раз не придётся вводить."""
    SPEC_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPEC_FILE.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return SPEC_FILE


# --------------------------------------------------------------------------
# Живая установка через COM (тот же приём, что в пункте 33: по одной команде)
# --------------------------------------------------------------------------
@dataclass
class HolderStep:
    """Одна команда и что ответил PowerMill."""

    command: str
    ok: bool
    note: str = ""


@dataclass
class HolderReport:
    """Что вышло: по шагам и честным итогом."""

    tool: str = ""
    spec: HolderSpec = field(default_factory=HolderSpec)
    steps: list[HolderStep] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(step.ok for step in self.steps)

    @property
    def failed(self) -> list[HolderStep]:
        return [step for step in self.steps if not step.ok]

    def format(self) -> str:
        lines = [f"Державка фрезы «{self.tool}»: {self.spec.describe()}", ""]
        for step in self.steps:
            mark = "✔" if step.ok else "✘"
            lines.append(f"{mark} {step.command}")
            if step.note and not step.ok:
                lines.append(f"    {step.note}")
        lines.append("")
        if self.ok:
            lines.append("Задана условная державка (два цилиндра). Это не твоя "
                         "оснастка: для точных выводов поставь свою державку "
                         "в PowerMill и повтори проверку.")
        else:
            lines.append("Не все команды державки прошли — проверка столкновений "
                         "может остаться недоступной. Что именно не прошло — "
                         "в строках с ✘.")
        if self.message:
            lines.append(self.message)
        return "\n".join(lines)


def apply_live(session, tool: str, spec: HolderSpec,
               log=None) -> HolderReport:
    """Задаёт хвостовик и патрон в живом PowerMill (по одной команде).

    `session` — объект с `execute(команда) -> (ok, текст)` (`src.pm_com.LiveSession`).
    Диалоги гасим и возвращаем как было: иначе окно ошибки блокирует ответ.
    """
    say = log or (lambda _text: None)
    report = HolderReport(tool=tool, spec=spec)
    if not tool:
        report.message = "не знаю, какой фрезе задавать державку — имя пустое"
        return report

    commands = ["DIALOGS MESSAGE OFF", "DIALOGS ERROR OFF"]
    commands += spec.lines(tool)
    for command in commands:
        ok, note = session.execute(command)
        report.steps.append(HolderStep(command, bool(ok), note))
        say(f"   {command}: " + ("ок" if ok else "ошибка"))
    for command in ("DIALOGS ERROR ON", "DIALOGS MESSAGE ON"):
        ok, note = session.execute(command)
        report.steps.append(HolderStep(command, bool(ok), note))
    return report

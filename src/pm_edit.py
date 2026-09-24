"""
Запись режимов резания в проект PowerMill (шаг 3.1 Уровня 3).

Что делает
----------
Считанные режимы (S — обороты, F — минутная подача, при желании F врезания)
записываются в **траектории твоего проекта**. Никакой магии: модуль собирает
PML-макрос, показывает его тебе ДО запуска, выполняет только после «да» и потом
**читает значения обратно**, печатая «было → стало».

Откуда взяты команды (не выдуманы)
----------------------------------
1. Параметры траектории — присваивание как в рабочих макросах форума Autodesk
   («Looking for the expression to reduce feedrates in a toolpath?»):

       ENTITY activeTp = entity('toolpath','')
       $activeTp.Feedrate.Cutting.Value = $newFeed
       $ent.SpindleSpeed.Value = 11000
       $ent.Feedrate.Plunging.Value = $newPlungeFeed

2. Команды активной траектории — из рабочего макроса на форуме Autodesk
   («Macro not using input», макрос автосоздания переходов):

       EDIT TPPAGE SWFeedSpeed
       EDIT RPM $rpm          // обороты
       EDIT FRATE $feed       // подача резания
       EDIT PRATE $plunge     // подача врезания

   Поэтому резервный способ у нас — именно эти команды, а не догадки.

3. Глубины ap/ae пишутся командой `EDIT PAR '<имя параметра>' <значение>`
   (руководство PowerMill). Имя зависит от стратегии: `EDIT PAR 'Stepover'`,
   `EDIT PAR 'Stepdown'`, а для Model Area Clearance понадобилось
   `EDIT PAR 'AreaClearance.ZHeights.Stepdown'`. Поэтому ap/ae автоматически
   пока НЕ пишем: сначала подтвердим имена параметров для твоих стратегий.

Модуль делает **оба** способа и печатает, какой сработал: если параметр не
изменился, выполняется команда, и результат снова читается. Так мы не гадаем,
а получаем факт — и в отчёте видно, чем именно записалось значение.

Правила безопасности (обещаны пользователю)
-------------------------------------------
* ничего не меняется молча: сначала предпросмотр команд, потом подтверждение;
* страховка — копия папки проекта до правки (`backup_project`);
* после записи значения читаются обратно и печатаются «было → стало»;
* файл результата — только ASCII (его пишет PowerMill в своей кодировке).
"""
from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from config import OUTPUT_DIR

EDIT_FILE = OUTPUT_DIR / "pm_edit.mac"
RESULT_FILE = OUTPUT_DIR / "pm_edit_result.txt"

# Параметры траектории, которые умеем писать: (имя в PML, ключ в записи)
PARAMS: tuple[tuple[str, str], ...] = (
    ("SpindleSpeed", "spindle"),
    ("Feedrate.Cutting", "feed"),
    ("Feedrate.Plunging", "plunge"),
)

# Резервные команды для активной траектории — из рабочего макроса Autodesk
# («Macro not using input»): EDIT TPPAGE SWFeedSpeed + EDIT RPM/FRATE/PRATE.
FALLBACK_COMMANDS: dict[str, str] = {
    "SpindleSpeed": 'EDIT RPM "{}"',
    "Feedrate.Cutting": 'EDIT FRATE "{}"',
    "Feedrate.Plunging": 'EDIT PRATE "{}"',
}

# Страница параметров, в которой живут обороты и подачи (см. тот же макрос).
FEED_PAGE = "EDIT TPPAGE SWFeedSpeed"

MARKER = "EDIT;"


@dataclass(frozen=True)
class SpeedFeed:
    """Что записать в одну траекторию. None — не трогать этот параметр."""

    toolpath: str
    spindle: int | None = None
    feed: int | None = None
    plunge: int | None = None

    def targets(self) -> list[tuple[str, str, int]]:
        """[(имя параметра PML, ключ, значение)] — только заданные."""
        pairs = (("SpindleSpeed", "spindle", self.spindle),
                 ("Feedrate.Cutting", "feed", self.feed),
                 ("Feedrate.Plunging", "plunge", self.plunge))
        return [(name, key, int(value)) for name, key, value in pairs
                if value is not None]


@dataclass
class EditResult:
    """Разобранная строка результата из файла, который пишет макрос."""

    toolpath: str
    param: str
    target: float
    was: float
    now: float
    method: str

    @property
    def ok(self) -> bool:
        tolerance = max(0.5, abs(self.target) * 0.001)
        return abs(self.now - self.target) <= tolerance

    def line(self) -> str:
        mark = "✔" if self.ok else "✘"
        return (f"  {mark} {self.toolpath}: {self.param} "
                f"{_fmt(self.was)} → {_fmt(self.now)} (нужно {_fmt(self.target)}, "
                f"способ: {self.method})")


def _fmt(value: float) -> str:
    return f"{value:.0f}" if float(value).is_integer() else f"{value:g}"


# --------------------------------------------------------------------------
# Сборка макроса
# --------------------------------------------------------------------------
def _pml_access(toolpath_var: str, param: str) -> str:
    return f"${toolpath_var}.{param}.Value"


def edit_macro(edits: list[SpeedFeed], result_file: Path | str = RESULT_FILE,
               stamp: str | None = None) -> str:
    """Текст PML-макроса: записать режимы и проверить их чтением обратно."""
    out_file = str(result_file).replace("\\", "/")
    when = stamp or time.strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        "// ============================================================",
        "//  PowerMill AI — запись режимов резания (шаг 3.1)",
        f"//  Собрано: {when}",
        "//  Макрос меняет ТОЛЬКО подачу и обороты указанных траекторий.",
        "//  Запуск: PowerMill -> лента «Макрос» -> Выполнить -> этот файл.",
        "// ============================================================",
        "",
        "// Переменные живут в сессии PowerMill — сбрасываем перед работой.",
        "RESET LOCALVARS",
        "",
        f"STRING $pm_result_file = '{out_file}'",
        "FILE OPEN $pm_result_file FOR WRITE AS out",
        'FILE WRITE "PM_EDIT_RESULT" TO out',
        "",
        "INT $pm_ok = 0",
        "INT $pm_total = 0",
    ]

    for index, edit in enumerate(edits, 1):
        prefix = f"e{index}"
        lines += [
            "",
            f"// ---- {edit.toolpath} ----",
            f"ENTITY ${prefix}_tp = entity('toolpath','{edit.toolpath}')",
        ]
        # 1) запоминаем «было»
        for param, _key in PARAMS:
            lines.append(f"REAL ${prefix}_{_short(param)}0 = {_pml_access(prefix + '_tp', param)}")
        # 2) пишем параметрами
        for param, _key, value in edit.targets():
            lines.append(f"{_pml_access(prefix + '_tp', param)} = {value}")
        # 3) читаем «стало»
        for param, _key in PARAMS:
            lines.append(f"REAL ${prefix}_{_short(param)}1 = {_pml_access(prefix + '_tp', param)}")
        # 4) отчёт по каждому параметру + резервная команда
        for param, _key, value in edit.targets():
            short = _short(param)
            lines += [
                f"$pm_total = $pm_total + 1",
                f'STRING ${prefix}_r_{short} = "{MARKER}{edit.toolpath};{param};'
                f'{value};" + STRING(${prefix}_{short}0) + ";" + STRING(${prefix}_{short}1)'
                f' + ";param"',
                f"FILE WRITE ${prefix}_r_{short} TO out",
                f"PRINT ${prefix}_r_{short}",
                f'IF ${prefix}_{short}1 == {value} {{ $pm_ok = $pm_ok + 1 }}',
            ]
            fallback = FALLBACK_COMMANDS.get(param)
            if fallback:
                lines += [
                    f"IF ${prefix}_{short}1 != {value} {{",
                    f"    ACTIVATE TOOLPATH ${prefix}_tp",
                    "    " + FEED_PAGE,
                    "    " + fallback.format(value),
                    f"    REAL ${prefix}_{short}2 = {_pml_access(prefix + '_tp', param)}",
                    f'    STRING ${prefix}_c_{short} = "{MARKER}{edit.toolpath};{param};'
                    f'{value};" + STRING(${prefix}_{short}0) + ";" + STRING(${prefix}_{short}2)'
                    f' + ";command"',
                    f"    FILE WRITE ${prefix}_c_{short} TO out",
                    f"    PRINT ${prefix}_c_{short}",
                    f"    IF ${prefix}_{short}2 == {value} {{ $pm_ok = $pm_ok + 1 }}",
                    "}",
                ]

    lines += [
        "",
        "FILE CLOSE out",
        "",
        'STRING $pm_sum = "PowerMill AI: записей удалось " + STRING($pm_ok) + " из " '
        '+ STRING($pm_total) + ". Подробности: " + $pm_result_file',
        "PRINT $pm_sum",
        "IF $pm_ok == $pm_total {",
        "    MESSAGE INFO $pm_sum",
        "} ELSE {",
        "    MESSAGE WARN $pm_sum",
        "}",
        "",
    ]
    return "\n".join(lines)


def _short(param: str) -> str:
    """Короткое имя для переменных PML: SpindleSpeed -> s, Feedrate.* -> f/p."""
    return {"SpindleSpeed": "s", "Feedrate.Cutting": "f",
            "Feedrate.Plunging": "p"}.get(param, param[:1].lower())


def preview(edits: list[SpeedFeed]) -> list[str]:
    """Что именно будет сделано — человеческим текстом, до запуска."""
    lines: list[str] = []
    for edit in edits:
        lines.append(f"  {edit.toolpath}:")
        for param, _key, value in edit.targets():
            lines.append(f"      {param} → {value}   ($tp.{param}.Value = {value})")
        if not edit.targets():
            lines.append("      (нечего менять)")
    return lines


def write_macro(edits: list[SpeedFeed], path: Path | str = EDIT_FILE,
                result_file: Path | str = RESULT_FILE) -> Path:
    """Пишет макрос правки (windows-переводы строк, как у макросов PowerMill)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = edit_macro(edits, result_file=result_file).replace("\n", "\r\n")
    target.write_bytes(text.encode("utf-8"))
    return target


# --------------------------------------------------------------------------
# Разбор результата
# --------------------------------------------------------------------------
RESULT_LINE_RE = re.compile(
    r"^" + re.escape(MARKER) +
    r"(?P<toolpath>[^;]+);(?P<param>[^;]+);(?P<target>[-0-9.eE+]+);"
    r"(?P<was>[-0-9.eE+]+);(?P<now>[-0-9.eE+]+);(?P<method>[A-Za-z]+)\s*$")


def parse_result(text: str) -> list[EditResult]:
    """Строки результата, которые записал макрос (их же он печатал в окно)."""
    found: list[EditResult] = []
    for raw in text.splitlines():
        match = RESULT_LINE_RE.match(raw.strip())
        if not match:
            continue
        try:
            found.append(EditResult(
                toolpath=match.group("toolpath").strip(),
                param=match.group("param").strip(),
                target=float(match.group("target")),
                was=float(match.group("was")),
                now=float(match.group("now")),
                method={"param": "параметр траектории",
                        "command": "команда PowerMill (EDIT RPM/FRATE)"}.get(
                            match.group("method"), match.group("method")),
            ))
        except ValueError:
            continue
    return found


def format_results(results: list[EditResult]) -> str:
    """Таблица «было → стало» для консоли и отчёта."""
    if not results:
        return ("  Пока нет данных от макроса: файл результата пуст или макрос ещё "
                "не запускался.")
    lines = [result.line() for result in results]
    good = sum(1 for r in results if r.ok)
    lines.append("")
    lines.append(f"  Итого: записано {good} из {len(results)} значений.")
    if good < len(results):
        lines.append("  Что делать с неудачными: пришли этот отчёт — подберём "
                     "точную команду для твоей стратегии (она зависит от типа "
                     "траектории в PowerMill 2026).")
    return "\n".join(lines)


def last_results(path: Path | str = RESULT_FILE) -> tuple[list[EditResult], str]:
    """Читает файл результата: (результаты, пояснение)."""
    file = Path(path)
    if not file.exists():
        return [], f"файла ещё нет ({file})"
    text = file.read_text(encoding="utf-8", errors="replace")
    results = parse_result(text)
    age = time.time() - file.stat().st_mtime
    if age > 3600:
        when = time.strftime("%d.%m %H:%M", time.localtime(file.stat().st_mtime))
        return results, f"файл от {when} — если проект другой, запусти макрос заново"
    return results, f"свежий файл ({file.name})"


# --------------------------------------------------------------------------
# Страховка: копия проекта
# --------------------------------------------------------------------------
def backup_project(folder: Path | str) -> Path:
    """Копия папки проекта рядом с оригиналом: «Деталь» -> «Деталь_AI_дата».

    Оригинал не трогаем — так обещано в правилах безопасности. Копируем именно
    на диске (PowerMill открытый проект при этом не мешает: чтение папки).
    """
    source = Path(folder)
    if not source.exists() or not source.is_dir():
        raise NotADirectoryError(f"нет такой папки: {source}")
    stamp = time.strftime("%Y%m%d_%H%M")
    target = source.with_name(f"{source.name}_AI_{stamp}")
    counter = 1
    while target.exists():
        counter += 1
        target = source.with_name(f"{source.name}_AI_{stamp}_{counter}")
    shutil.copytree(source, target)
    return target


def project_copy_hint() -> str:
    """Что сказать пользователю, если папку проекта указывать не хочется."""
    return ("Если путь вводить не хочется — сделай копию сам в PowerMill: "
            "Файл → Сохранить как → добавь в имя «_AI». Только после этого "
            "запускай макрос правки.")

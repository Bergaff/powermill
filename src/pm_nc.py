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
* постпроцессор должен соответствовать станку. Если он не задан, PowerMill берёт
  тот, что стоит в настройках проекта, — а в новом (пустом) проекте его нет, и
  вывод падает с «должен быть задан файл постпроцессора». Поэтому файл .pmoptz
  лучше указать: выбранный путь запоминается (`DATA_ROOT/postprocessor.txt`), и
  дальше и пункт 36, и поток берут его сами;
* порядок траекторий в программе — тот, что указан в плане (технолог может
  поменять);
* мы не проверяем кадры NC-файла — для этого есть NCSIMUL (он у тебя есть) или
  симуляция самого PowerMill (пункт 35 — это проверки траекторий, не NC).

Если программы с таким именем в проекте уже есть — по умолчанию не перезаписываем,
а сообщаем: так случайно не потеряется ранее выведенная программа.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from config import DATA_ROOT, OUTPUT_DIR
from src import pml_files

MACRO_FILE = OUTPUT_DIR / "pm_nc.mac"
RESULT_FILE = OUTPUT_DIR / "pm_nc_result.txt"
STEP_MARK = "NC;"

# Постпроцессор, выбранный человеком: одна строка с путём к .pmoptz рядом с
# данными (вне Git). Его можно вписать руками — и пункт 36, и поток возьмут
# этот путь сами, без вопросов.
POST_FILE = DATA_ROOT / "postprocessor.txt"

# Каким способом удалось задать постпроцессор (тоже вне Git).
TAPE_FILE = DATA_ROOT / "tape_option_form.txt"


@dataclass(frozen=True)
class TapeForm:
    """Способ задать постпроцессор у NC-программы.

    Зачем их несколько: на живом PowerMill 2026 короткая команда
    `EDIT NCPROGRAM 'имя' TAPEOPTIONS 'путь'` прошла без ошибки, но пост НЕ
    встал — вывод упал с «должен быть задан файл постпроцессора». Способы ниже
    собраны из рабочих макросов Autodesk (форумы 7109100, 8441844, 6481783,
    6584012, 9808487): где-то нужен `FILEOPEN`, где-то подтверждение окна
    (`FORM ACCEPT SelectOptionFile`), где-то `NCSELECTED APPLY/ACCEPT`.
    Пункт 36 пробует их по очереди и запоминает сработавший.
    """

    key: str
    title: str
    commands: tuple[str, ...] = ()

    def lines(self, name: str, post: str) -> list[str]:
        return [command.format(name=name, post=post) for command in self.commands]


TAPE_FORMS: tuple[TapeForm, ...] = (
    TapeForm("selected_fileopen",
             "через выбранную программу: TAPEOPTIONS FILEOPEN + APPLY/ACCEPT",
             ("ACTIVATE NCPROGRAM '{name}'",
              "EDIT NCPROGRAM SELECTED TAPEOPTIONS FILEOPEN '{post}'",
              "NCSELECTED APPLY",
              "NCSELECTED ACCEPT")),
    TapeForm("select_option_file",
             "установка поста + подтверждение окна выбора (FORM ACCEPT)",
             ("EDIT NCPROGRAM '{name}' TAPEOPTIONS '{post}'",
              "FORM ACCEPT SelectOptionFile")),
    TapeForm("fileopen_accept",
             "TAPEOPTIONS FILEOPEN + подтверждение списка траекторий",
             ("EDIT NCPROGRAM '{name}' TAPEOPTIONS FILEOPEN '{post}'",
              "NCTOOLPATH APPLY",
              "NCTOOLPATH ACCEPT")),
    TapeForm("selected_plain",
             "через выбранную программу: TAPEOPTIONS + APPLY/ACCEPT",
             ("ACTIVATE NCPROGRAM '{name}'",
              "EDIT NCPROGRAM SELECTED TAPEOPTIONS '{post}'",
              "NCSELECTED APPLY",
              "NCSELECTED ACCEPT")),
    TapeForm("preferences",
             "пост как настройка проекта (NC preferences)",
             ("EDIT NCPROGRAM PREFERENCES TAPEOPTIONS FILEOPEN '{post}'",
              "NCPREFERENCES ACCEPT")),
    TapeForm("plain",
             "короткая форма (у тебя не сработала — оставлена для полноты)",
             ("EDIT NCPROGRAM '{name}' TAPEOPTIONS '{post}'",)),
)

DEFAULT_FORM = "selected_fileopen"


def form_by_key(key: str) -> TapeForm | None:
    for form in TAPE_FORMS:
        if form.key == key:
            return form
    return None


def saved_form() -> TapeForm | None:
    """Способ, который уже срабатывал (или None)."""
    if not TAPE_FILE.exists():
        return None
    try:
        lines = pml_files.read(TAPE_FILE).splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return form_by_key(stripped)
    return None


def remember_form(form: TapeForm | str) -> Path:
    """Запоминает сработавший способ — следующий раз начнём с него."""
    key = form.key if isinstance(form, TapeForm) else str(form)
    stamp = ("# сработавший способ задать постпроцессор (живой PowerMill)\n"
             f"{key}\n")
    TAPE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return pml_files.write(TAPE_FILE, stamp)


def attempt_order() -> list[TapeForm]:
    """Порядок попыток: сначала тот, что сработал раньше, потом остальные."""
    saved = saved_form()
    order = [saved] if saved is not None else []
    for form in TAPE_FORMS:
        if saved is None or form.key != saved.key:
            order.append(form)
    return order


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


def saved_post() -> Path | None:
    """Постпроцессор, выбранный раньше (`DATA_ROOT/postprocessor.txt`).

    Читаем как есть: если файл переехал или его удалили, так и скажем при
    проверке плана («файла постпроцессора нет»), а не подсунем битый путь молча.
    """
    try:
        text = POST_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip().strip('"')
        if line and not line.startswith("#"):
            return Path(line)
    return None


def save_post(path: Path | str) -> Path:
    """Запоминает постпроцессор для следующих запусков (пункт 36 и поток)."""
    POST_FILE.parent.mkdir(parents=True, exist_ok=True)
    POST_FILE.write_text(str(path).replace("\\", "/") + "\n", encoding="utf-8")
    return POST_FILE


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


def build_macro(plan: NcPlan, known_programs: list[str] | None = None,
                form: TapeForm | None = None) -> str:
    """Макрос вывода NC: создать программу, вложить траектории, записать файл.

    `known_programs` — программы, которые уже есть в проекте (их имена читает
    пункт 36 через COM). Если имя совпадает и перезапись не разрешена, макрос
    ничего не делает и честно об этом пишет.

    Две вещи, которые легко испортить, и которые здесь учтены:

    * **объявления только на верхнем уровне** — внутри IF/ELSE PowerMill
      допускает лишь присваивание (иначе «local variable is already defined»);
    * **вывод файла** (`ACTIVATE NCPROGRAM … KEEP NCPROGRAM ;`) может спросить
      подтверждение — тогда макрос отвечает `YES`, как это сделано в рабочих
      макросах Autodesk. Строку «файл выведен» макрос пишет уже ПОСЛЕ вывода,
      поэтому её наличие — доказательство, что вывод прошёл; нет строки — значит
      не прошёл, и это будет видно в отчёте.
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
        "// Окна ошибок гасим: неверная команда тогда останавливает макрос молча,",
        "// а пункт 36 видит по отметкам, что не прошло, и пробует другой способ.",
        "DIALOGS MESSAGE OFF",
        "DIALOGS ERROR OFF",
        "",
        "// Объявления — заранее, до IF: внутри блоков PowerMill разрешает только",
        "// присваивание.",
        f"STRING $pm_res = '{out}'",
        'STRING $pm_tag = "PM_NC_RESULT"',
        f'STRING $pm_head = "PowerMill AI: вывод NC-программы {plan.name}"',
        'STRING $pm_fin = "Вывод NC закончен: " + $pm_res',
        'STRING $pm_prj = ""',
        'STRING $pm_prjline = ""',
        'STRING $pm_dup = ""',
        'STRING $pm_created = ""',
        'STRING $pm_add = ""',
        'STRING $pm_file = ""',
        'STRING $pm_post = ""',
        'STRING $pm_pp = ""',
        'STRING $pm_num = ""',
        'STRING $pm_keep = ""',
        'STRING $pm_out = ""',
        'STRING $pm_ok = "no"',
        "",
        "FILE OPEN $pm_res FOR WRITE AS ncout",
        "FILE WRITE $pm_tag TO ncout",
        "FILE WRITE $pm_head TO ncout",
        "",
        "// папка проекта — по ней сценарий проверит, появился ли файл NC на диске",
        "$pm_prj = project_pathname(0)",
        f'$pm_prjline = "{STEP_MARK}project;info;" + $pm_prj',
        "FILE WRITE $pm_prjline TO ncout",
        "",
    ]

    # программа с таким именем уже есть — по умолчанию не перезаписываем
    if known and not plan.overwrite:
        lines += [
            f"IF ENTITY_EXISTS('ncprogram', '{safe_name}') {{",
            f'    $pm_dup = "{STEP_MARK}exists;fail;программа «{plan.name}» уже есть в '
            'проекте — включи перезапись (overwrite), если нужно заменить"',
            "    FILE WRITE $pm_dup TO ncout",
            "} ELSE {",
        ]
        inner = "    "
    else:
        inner = ""

    if plan.overwrite:
        lines += [
            f"{inner}// перезапись разрешена: старую программу с таким именем удаляем",
            f"{inner}IF ENTITY_EXISTS('ncprogram', '{safe_name}') {{",
            f"{inner}    DELETE NCPROGRAM '{safe_name}'",
            f"{inner}}}",
        ]

    lines += [
        f"{inner}CREATE NCPROGRAM '{safe_name}'",
        f'{inner}$pm_created = "{STEP_MARK}create;ok;{plan.name}: программа создана"',
        f"{inner}FILE WRITE $pm_created TO ncout",
        f"{inner}ACTIVATE NCPROGRAM '{safe_name}'",
    ]

    for toolpath in plan.toolpaths:
        safe_tp = toolpath.replace("'", "''")
        lines += [
            f"    // траектория: {toolpath}",
            f"    IF ENTITY_EXISTS('toolpath', '{safe_tp}') {{",
            f"        EDIT NCPROGRAM ; APPEND TOOLPATH '{safe_tp}'",
            f'        $pm_add = "{STEP_MARK}append;ok;{toolpath}"',
            "    } ELSE {",
            f'        $pm_add = "{STEP_MARK}append;fail;{toolpath}: такой траектории в проекте нет"',
            "    }",
            "    FILE WRITE $pm_add TO ncout",
        ]

    if plan.filename is not None:
        target = str(plan.filename).replace("\\", "/")
        lines += [
            "    // путь выходного файла",
            f"    EDIT NCPROGRAM '{safe_name}' FILENAME '{target}'",
            f'    $pm_file = "{STEP_MARK}filename;ok;{target}"',
            "    FILE WRITE $pm_file TO ncout",
        ]

    if plan.postprocessor is not None:
        post = str(plan.postprocessor).replace("\\", "/")
        chosen = form or form_by_key(DEFAULT_FORM) or TAPE_FORMS[0]
        form_lines = chosen.lines(safe_name, post)
        lines += [
            "    // постпроцессор (файл .pmoptz). Без него PowerMill отказывается",
            "    // писать файл: «должен быть задан файл постпроцессора».",
            f"    // Способ установки: {chosen.title}",
            f"    $pm_pp = '{post}'",
            f'    $pm_form = "NC;tape_form;info;{chosen.key} — {chosen.title}"',
            "    FILE WRITE $pm_form TO ncout",
            "    IF file_exists($pm_pp) {",
        ] + [f"        {line}" for line in form_lines] + [
            f'        $pm_post = "{STEP_MARK}postprocessor;ok;{post}"',
            "    } ELSE {",
            f'        $pm_post = "{STEP_MARK}postprocessor;fail;файла постпроцессора нет: '
            f'{post} — вывод отменён, PowerMill без него NC не пишет"',
            '        $pm_ok = "no"',
            "    }",
            "    FILE WRITE $pm_post TO ncout",
        ]

    lines += [
        f"    EDIT NCPROGRAM '{safe_name}' NUMBER {int(plan.number)}",
        f'    $pm_num = "{STEP_MARK}number;ok;{int(plan.number)}"',
        "    FILE WRITE $pm_num TO ncout",
        "    DEACTIVATE NCPROGRAM",
        "",
        "    // ---- вывод файла: KEEP NCPROGRAM = записать NC ----",
        f'    $pm_keep = "{STEP_MARK}keep;info;вывожу файл: KEEP NCPROGRAM"',
        "    FILE WRITE $pm_keep TO ncout",
        '    $pm_ok = "yes"',
    ]

    if known and not plan.overwrite:
        lines.append("}")

    # отчёт закрываем ДО вывода файла: если PowerMill задумается, отчёт уже целый
    lines += [
        "",
        "FILE CLOSE ncout",
        "",
        'IF $pm_ok == "yes" {',
        "    // Вывод файла. Если PowerMill спросит подтверждение — ответит строка YES",
        "    // (так сделано в рабочих макросах Autodesk: ACTIVATE … KEEP NCPROGRAM ; YES).",
        f"    ACTIVATE NCPROGRAM '{safe_name}' KEEP NCPROGRAM ;",
        "    YES",
        "    // строку о выводе пишем ПОСЛЕ вывода — она и есть доказательство",
        "    FILE OPEN $pm_res FOR APPEND AS nc_after",
        f'    $pm_out = "{STEP_MARK}write;ok;файл NC выведен"',
        "    FILE WRITE $pm_out TO nc_after",
        "    FILE CLOSE nc_after",
        "}",
        "DIALOGS ERROR ON",
        "DIALOGS MESSAGE ON",
        "PRINT $pm_fin",
        "MESSAGE INFO $pm_fin",
    ]
    # Дескрипторы уникальны на запуск: см. src/pml_files.unique_handles.
    return pml_files.unique_handles("\n".join(lines)) + "\n"


def write_macro(plan: NcPlan, path: Path | str = MACRO_FILE,
                known_programs: list[str] | None = None,
                form: TapeForm | None = None) -> Path:
    """Пишет макрос вывода NC (CP1251, CRLF)."""
    target = Path(path)
    pml_files.write(target, build_macro(plan, known_programs=known_programs,
                                        form=form))
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
    "project": "Папка проекта",
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


def project_path(steps: list[tuple[str, str, str]]) -> Path | None:
    """Папка проекта из отчёта макроса (`project_pathname(0)`)."""
    for step, _status, detail in steps:
        if step == "project" and detail:
            return Path(detail.strip().replace("\\", "/"))
    return None


NC_SUFFIXES = (".tap", ".nc", ".cnc", ".h", ".mpf", ".txt", ".iso", ".gcode")


def find_written_file(folder: Path | None, before: float,
                      suffixes: tuple[str, ...] = NC_SUFFIXES) -> Path | None:
    """Ищет файл NC, который PowerMill записал после `before`.

    PowerMill кладёт вывод в папку `ncprograms` проекта (имя — как у программы).
    Если файла нет — так и скажем, вместо «наверное, вывелось».
    """
    if not folder:
        return None
    folders = [folder / "ncprograms", folder]
    newest: Path | None = None
    for candidate in folders:
        if not candidate.exists():
            continue
        try:
            files = [path for path in candidate.iterdir()
                     if path.is_file() and path.suffix.lower() in suffixes
                     and path.stat().st_mtime >= before - 2]
        except OSError:
            continue
        for path in files:
            if newest is None or path.stat().st_mtime > newest.stat().st_mtime:
                newest = path
    return newest


def written_file_info(path: Path | str | None) -> tuple[Path, int] | None:
    """Файл и его размер — или None, если файла нет/диск недоступен.

    Проверять обязательно: диск E: может быть не подключён, а PowerMill ответил
    «записал». Обещать файл, которого нет, нельзя.
    """
    if not path:
        return None
    try:
        file = Path(path)
        return file, file.stat().st_size
    except OSError:
        return None


def default_filename(project_folder: Path | str | None, name: str,
                     suffix: str = ".tap") -> Path:
    """Куда писать NC: папка проекта (ncprograms) или наш output."""
    base = Path(project_folder) if project_folder else DATA_ROOT / "output" / "nc"
    return base / "ncprograms" / f"{name}{suffix}"


# Подсказки к найденным постам: что это за пост. Мы не выбираем пост за
# человека (стойку знает только он), но объясняем, с чего обычно начинают.
POST_HINTS = {
    "fanuc": "самый распространённый: Fanuc и совместимые стойки — обычно берут за основу",
    "heidenhain": "для стоек Heidenhain (диалоговое программирование)",
    "haas": "для станков Haas",
    "siemens": "для стоек Siemens Sinumerik",
    "makino": "для станков Makino",
    "matsuura": "для станков Matsuura",
    "fidia": "для станков Fidia",
    "hurco": "для станков Hurco WinMax",
    "elexa": "для стоек Elexa",
}


def post_hint(path: Path | str) -> str:
    """Одна строка: что это за постпроцессор (пусто — не знаем, так и молчим)."""
    stem = Path(path).stem.lower()
    for key, text in POST_HINTS.items():
        if key in stem:
            return text
    return ""


def post_hints(paths: list[Path]) -> list[str]:
    """Пояснения к списку постов — в том же порядке."""
    return [post_hint(path) for path in paths]


def post_dirs() -> list[Path]:
    """Где PowerMill и утилита постпроцессоров держат .pmoptz.

    По опыту и документации Autodesk файлы постпроцессоров лежат:

    * в установке PowerMill — подпапка `file\\proc` (у нас PowerMill на E:);
    * у «Manufacturing Post Processor Utility» (идёт с PowerMill) —
      `C:\\Users\\Public\\Documents\\Autodesk\\Manufacturing Post Processor Utility
      <версия>\\Generic` (там generic-посты: Fanuc, Heidenhain, Siemens…);
    * у старых версий — `C:\\dcam\\config\\ductpost`;
    * плюс наша папка данных (человек мог просто положить файл рядом).
    """
    dirs: list[Path] = [DATA_ROOT, DATA_ROOT / "post", DATA_ROOT / "output" / "post",
                        Path("C:/dcam/config/ductpost"),
                        Path("C:/dcam/config/postprocessor")]
    docs: list[Path] = []
    for var in ("PUBLIC", "USERPROFILE"):
        base = os.environ.get(var)
        if base:
            docs.append(Path(base) / "Documents")
    for base in docs:
        for pattern in ("Autodesk/Manufacturing Post Processor Utility*",
                        "Manufacturing Post Processor Utility*",
                        "Autodesk/PowerMill*"):
            try:
                dirs.extend(sorted(base.glob(pattern)))
            except OSError:
                continue
    for letter in "CDEFGH":
        root = Path(f"{letter}:/")
        try:
            if not root.exists():
                continue
        except OSError:
            continue
        for pattern in ("powermill*", "PowerMill*", "Autodesk/PowerMill*",
                        "Program Files/Autodesk/PowerMill*",
                        "Program Files (x86)/Autodesk/PowerMill*"):
            try:
                dirs.extend(sorted(root.glob(pattern)))
            except OSError:
                continue
    return [folder for folder in dirs if folder.exists()]


def find_postprocessors(extra_dirs: list[Path] | None = None,
                        limit: int = 40) -> list[Path]:
    """Ищет файлы постпроцессоров (.pmoptz) — чтобы предложить выбор в мастере."""
    roots: list[Path] = list(extra_dirs or [])
    saved = saved_post()
    if saved is not None:
        roots.append(saved.parent)                  # там, где он лежал в прошлый раз
    roots.extend(post_dirs())

    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> bool:
        key = str(path).lower()
        if key in seen:
            return False
        seen.add(key)
        found.append(path)
        return len(found) >= limit

    for folder in roots:
        try:
            folder = Path(folder)
        except (TypeError, ValueError):
            continue
        if not folder.is_dir():
            continue
        # прямо в папке + известные подпапки, потом — неглубоко внутрь
        # (в утилите постов они разложены по станкам)
        shallow = [folder, folder / "file" / "proc", folder / "file" / "post",
                   folder / "Generic", folder / "postprocessor", folder / "post"]
        for candidate in shallow:
            if not candidate.is_dir():
                continue
            try:
                for path in sorted(candidate.glob("*.pmoptz")):
                    if add(path):
                        return found[:limit]
            except OSError:
                continue
        for pattern in ("*/*.pmoptz", "*/*/*.pmoptz", "*/*/*/*.pmoptz"):
            try:
                for path in sorted(folder.glob(pattern)):
                    if add(path):
                        return found[:limit]
            except OSError:
                continue
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
        lines.append("  4. Постпроцессор: НЕ задан — берётся из настроек проекта")
        lines.append("     (в новом проекте его нет, и PowerMill откажет: «должен быть"
                     " задан файл постпроцессора»)")
    lines.append("  5. Вывод файла: ACTIVATE NCPROGRAM … KEEP NCPROGRAM ;"
                 " (если PowerMill спросит подтверждение, макрос ответит «Да»)")
    if plan.overwrite:
        lines.append("  6. Перезапись: одноимённая программа в проекте будет удалена")
    return lines

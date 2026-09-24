"""
Панель «PowerMill AI» на ленте PowerMill (пункт 34).

Зачем
-----
До сих пор запуск был «через меню батников»: удобно, но каждый раз надо уходить
из PowerMill в окно консоли. Кнопки на ленте убирают этот шаг: нажал — и
запустился нужный сценарий.

Как это делается без C# и без плагина
-------------------------------------
У PowerMill есть штатные команды работы с лентой (с форума Autodesk):

    EDIT CUSTOMRIBBON RESET
    EDIT CUSTOMRIBBON IMPORT FILEOPEN "<файл.xml>"
    EDIT CUSTOMRIBBON APPLY
    FORM RIBBON TAB UICATEGORY        // перейти на свою вкладку

Сама настройка ленты лежит в файле пользователя
`%LOCALAPPDATA%\\Autodesk\\PowerMill*\\ribbon_customisation.xml`.

Формат этого XML Autodesk не документирует, поэтому мы его **не выдумываем**:
модуль находит в твоём файле уже существующую кнопку с макросом и клонирует её
под наши кнопки, меняя только подписи и путь к макросу. Если такой кнопки в
файле нет — ничего не меняем, а пишем в отчёт понятную инструкцию, как добавить
кнопку руками (это 6 кликов в самом PowerMill).

Каждая кнопка запускает маленький макрос-запускатель (`OLE FILEACTION`), а тот
открывает наш батник. То есть панель — это просто удобный вход в уже готовые
сценарии: ассистент, режимы резания, фреза, черновая операция, снимок проекта.
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR
from src import pml_files, pm_macro

REPORT_FILE = OUTPUT_DIR / "pm_ribbon_report.txt"
RIBBON_TAB_LABEL = "PowerMill AI"

# Кнопки панели: (подпись, имя макроса, что запускает, подсказка)
RIBBON_BUTTONS: tuple[tuple[str, str, str, str], ...] = (
    ("Ассистент (вопрос)", "PM_AI_ASK.mac", "PM_AI_ASK.mac",
     "Спросить ассистента, не выходя из PowerMill"),
    ("Чат в браузере", "PM_AI_CHAT.mac", "scripts\\chat_ui.bat",
     "Интерфейс с прогрессом и отчётами (пункт 32)"),
    ("Режимы резания", "PM_AI_CUTTING.mac", "start_cutting.bat",
     "Калькулятор S/F по материалу и фрезе"),
    ("Фреза в проект", "PM_AI_TOOL.mac", "scripts\\probe_tool.bat",
     "Создать фрезу и узнать рабочее слово (пункт 33)"),
    ("Черновая операция", "PM_AI_OPERATION.mac", "scripts\\make_operation.bat",
     "Инструмент + заготовка + траектория (пункт 31)"),
    ("Снимок проекта", "PM_AI_SNAPSHOT.mac", "PM_AI_SNAPSHOT.mac",
     "Ассистент узнает имена объектов проекта"),
)

# Как в файле ленты могут называться атрибуты подписи и «нажми меня»
LABEL_ATTRS = ("label", "name", "text", "caption", "title", "tooltip", "description")
PATH_SUFFIX = (".mac", ".bat", ".exe")


def launcher_macro(bat_relative: str) -> str:
    """Макрос-запускатель: одна команда OLE FILEACTION на нужный батник."""
    if bat_relative.lower().endswith(".mac"):
        # «кнопка ассистента» и «снимок» — это наши обычные макросы, не батники
        target = Path(pm_macro.OUTPUT_DIR) / bat_relative
    else:
        target = Path(pm_macro.OUTPUT_DIR).parent / bat_relative
    launcher = pm_macro._win_path(target)                 # noqa: SLF001 (осознанно)
    return (
        "// Запускается кнопкой с ленты PowerMill (пункт 34).\n"
        "RESET LOCALVARS\n"
        f"STRING $launcher = '{launcher}'\n"
        "OLE FILEACTION 'OPEN' $launcher\n"
    )


def write_launcher_macros(folder: Path | None = None) -> list[Path]:
    """Пишет макросы-запускатели для кнопок панели (CP1251, CRLF)."""
    target_dir = Path(folder or pm_macro.MACRO_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for _label, macro_name, bat, _hint in RIBBON_BUTTONS:
        if bat.lower().endswith(".mac"):
            continue                                      # ассистент/снимок уже есть
        written.append(pml_files.write(target_dir / macro_name, launcher_macro(bat)))
    return written


# --------------------------------------------------------------------------
# Файл настройки ленты
# --------------------------------------------------------------------------
def find_ribbon_file() -> Path | None:
    """Ищет файл настройки ленты в профиле пользователя (Windows).

    Известный путь с форума Autodesk:
    `C:\\Users\\<ты>\\AppData\\Local\\Autodesk\\PowerMill\\ribbon_customisation.xml`.
    Версии PowerMill могут класть файл в папку со своим номером, поэтому ищем
    по шаблону, а не по одному жёсткому пути.
    """
    roots: list[Path] = []
    for variable in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(variable)
        if base:
            roots.append(Path(base) / "Autodesk")
    for root in roots:
        if not root.exists():
            continue
        found = sorted(root.glob("PowerMill*/ribbon_customisation.xml"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if found:
            return found[0]
        found = sorted(root.glob("PowerMill*/**/ribbon_customisation.xml"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if found:
            return found[0]
    return None


def _read_xml(path: Path) -> tuple[str, str]:
    """Читает XML вместе с кодировкой (Autodesk пишет и UTF-8, и UTF-16)."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _write_xml(path: Path, text: str, encoding: str) -> None:
    if encoding == "utf-16":
        path.write_bytes(text.encode("utf-16"))
    else:
        path.write_bytes(text.encode("utf-8"))


def _local(tag: str) -> str:
    return tag.split("}")[-1].lower()


def structure_lines(root: ET.Element, limit: int = 60) -> list[str]:
    """Короткое описание структуры файла — видно, что там вообще есть."""
    lines: list[str] = []
    for element in root.iter():
        if len(lines) >= limit:
            lines.append("  …")
            break
        attrs = ", ".join(sorted(element.attrib)) or "—"
        label = ""
        for key, value in element.attrib.items():
            if any(word in key.lower() for word in LABEL_ATTRS) and str(value).strip():
                label = ' = "' + str(value)[:40] + '"'
                break
        lines.append(f"  <{_local(element.tag)}{label}>  атрибуты: {attrs}")
    return lines


def _macro_element(root: ET.Element):
    """Ищет элемент, который запускает макрос (в атрибуте путь .mac)."""
    for element in root.iter():
        for key, value in element.attrib.items():
            if str(value).strip().lower().endswith(PATH_SUFFIX):
                return element, key
    return None, ""


def _set_label(element: ET.Element, text: str) -> bool:
    """Проставляет подпись в те атрибуты, которые реально есть у элемента."""
    changed = False
    for key in list(element.attrib):
        if any(word in key.lower() for word in LABEL_ATTRS):
            element.set(key, text)
            changed = True
    if not changed:                                       # подписи не было — добавим
        element.set("label", text)
    return changed


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    """Карта «элемент -> его родитель» (в стандартном ElementTree её нет)."""
    return {child: parent for parent in root.iter() for child in parent}


def build_tab(root: ET.Element, buttons=None) -> tuple[bool, str]:
    """Добавляет вкладку с кнопками, клонируя существующую кнопку с макросом.

    Возвращает (получилось, пояснение). Ничего не выдумываем: если в файле нет
    ни одной кнопки с макросом, честно ничего не делаем.
    """
    buttons = buttons or RIBBON_BUTTONS
    sample, path_attr = _macro_element(root)
    if sample is None:
        return False, ("в файле ленты нет кнопки, запускающей макрос — "
                       "не меняю настройку (инструкция в отчёте)")

    parents = _parent_map(root)
    group = parents.get(sample)
    tab = parents.get(group) if group is not None else None
    if tab is None:
        return False, "структура файла непривычная: не нашёл вкладку с группой кнопок"

    new_tab = copy.deepcopy(tab)
    # оставляем в новой вкладке только первую группу — с нашими кнопками
    new_group = None
    for child in list(new_tab):
        if _local(child.tag) == _local(group.tag):
            new_group = child
            break
    if new_group is None:
        return False, "не нашёл группу внутри вкладки"

    for extra in list(new_tab):
        if extra is not new_group:
            new_tab.remove(extra)

    # в группе оставляем одну кнопку-образец и размножаем её под наши кнопки
    template = None
    for child in list(new_group):
        if _local(child.tag) == _local(sample.tag):
            template = child
            break
    if template is None:
        return False, "не нашёл кнопку внутри группы"
    for child in list(new_group):
        new_group.remove(child)

    for label, macro_name, _target, hint in buttons:
        button = copy.deepcopy(template)
        button.set(path_attr, _macro_path_for(macro_name))
        _set_label(button, label)
        for key in list(button.attrib):
            if any(word in key.lower() for word in ("tooltip", "description")):
                button.set(key, hint)
        child_tail = list(button)
        if child_tail:
            for child in child_tail:
                if any(word in _local(child.tag) for word in ("label", "text", "tooltip")):
                    child.text = label
        new_group.append(button)

    _set_label(new_tab, RIBBON_TAB_LABEL)
    _set_label(new_group, "Ассистент")
    # вкладку ставим последней: чужие настройки не переставляем
    root.append(new_tab)
    return True, f"добавил вкладку «{RIBBON_TAB_LABEL}» с {len(buttons)} кнопками"


def _macro_path_for(macro_name: str) -> str:
    """Путь к макросу кнопки — windows-вид, как в самой PowerMill."""
    return pm_macro._win_path(Path(pm_macro.MACRO_DIR) / macro_name)   # noqa: SLF001


# --------------------------------------------------------------------------
# Установка
# --------------------------------------------------------------------------
@dataclass
class RibbonResult:
    """Что получилось: файл ленты, вкладка, макросы-запускатели."""

    ribbon_file: Path | None = None
    backup: Path | None = None
    tab_added: bool = False
    applied: bool = False
    launchers: list[Path] = field(default_factory=list)
    structure: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines = ["Панель «PowerMill AI» на ленте (пункт 34)", ""]
        lines.append(f"Файл настройки ленты: {self.ribbon_file or '— не найден'}")
        if self.backup:
            lines.append(f"Копия прежней настройки: {self.backup}")
        lines.append("")
        lines.append("Макросы-запускатели (их вызывают кнопки):")
        lines.extend(f"  • {path.name}" for path in self.launchers)
        lines.append("")
        lines.append("Структура файла ленты (для истории):")
        lines.extend(self.structure or ["  — файл не найден"])
        lines.append("")
        if self.tab_added:
            lines.append("Вкладка с кнопками добавлена в файл настройки.")
        else:
            lines.append("Вкладку в файл настройки не добавлял.")
        lines.append("Применено в PowerMill: " + ("да" if self.applied else "нет"))
        if not self.applied:
            lines.append("  Если PowerMill был закрыт — он подхватит настройку при запуске.")
        for note in self.notes:
            lines.append("")
            lines.append(note)
        return "\n".join(lines)


def manual_note() -> str:
    """Инструкция, если автоматически вкладку добавить не удалось."""
    return (
        "Как добавить кнопку руками (6 кликов, официальный способ Autodesk):\n"
        "  1) в PowerMill: File -> Options -> Customise the Ribbon and Quick Access Toolbar;\n"
        "  2) в верхнем списке выбери «Macro button»;\n"
        "  3) Name: PowerMill AI, Description: ассистент, Picture: любая;\n"
        "  4) Macro -> Open -> выбери макрос из output\\pm_macros (например PM_AI_CHAT.mac);\n"
        "  5) нажми Add>> — создастся новая вкладка, переименуй её в «PowerMill AI»;\n"
        "  6) OK. Дальше кнопки добавляются так же.\n"
        "Файл этой настройки пришли в чат — тогда автоматический режим заработает:\n"
        "  %LOCALAPPDATA%\\Autodesk\\PowerMill\\ribbon_customisation.xml"
    )


def install(apply_in_powermill: bool = True, session=None) -> RibbonResult:
    """Добавляет вкладку на ленту и (если PowerMill запущен) применяет настройку."""
    result = RibbonResult()
    result.launchers = write_launcher_macros()

    ribbon_file = find_ribbon_file()
    result.ribbon_file = ribbon_file
    if ribbon_file is None:
        result.notes.append(
            "Файл настройки ленты не найден — значит, лента ещё не настраивалась.\n"
            "Открой в PowerMill: File -> Options -> Customise the Ribbon, закрой окно\n"
            "кнопкой OK (можно ничего не менять). После этого файл появится, и пункт 34\n"
            "добавит вкладку автоматически."
        )
        result.notes.append(manual_note())
        return result

    text, encoding = _read_xml(ribbon_file)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        result.notes.append(f"Файл ленты не разобрался как XML: {error}")
        result.notes.append(manual_note())
        return result

    result.structure = structure_lines(root)

    if RIBBON_TAB_LABEL in text:
        result.notes.append("Вкладка «PowerMill AI» в настройке уже есть — оставляю как есть.")
        return result

    ok, note = build_tab(root)
    result.notes.append(note)
    if not ok:
        result.notes.append(manual_note())
        return result

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup = ribbon_file.with_name(f"ribbon_customisation_backup_{stamp}.xml")
    shutil.copy2(ribbon_file, backup)
    result.backup = backup

    body = ET.tostring(root, encoding="unicode")
    if text.lstrip().startswith("<?xml"):
        declaration = text.lstrip().split("?>", 1)[0] + "?>"
        body = declaration + "\n" + body
    _write_xml(ribbon_file, body, encoding)
    result.tab_added = True

    if apply_in_powermill:
        if session is None:
            from src import pm_com

            session, _message = pm_com.connect()
        if session is None:
            result.notes.append("PowerMill сейчас не запущен: настройка применится при запуске.")
            return result
        commands = (
            f'EDIT CUSTOMRIBBON IMPORT FILEOPEN "{pm_macro._win_path(ribbon_file)}"',  # noqa: SLF001
            "EDIT CUSTOMRIBBON APPLY",
            "FORM RIBBON TAB UICATEGORY",
        )
        lines: list[str] = []
        for command in commands:
            try:
                good, answer = session.execute(command)
            except Exception as error:                     # noqa: BLE001
                good, answer = False, str(error)
            lines.append(f"{'✔' if good else '✘'} {command}")
            if answer:
                lines.append(f"    {answer}")
        result.applied = all(line.startswith("✔") for line in lines if line.startswith(("✔", "✘")))
        result.notes.append("Применение настройки в PowerMill:\n" + "\n".join(lines))
        if not result.applied:
            result.notes.append(
                "Если вкладка не появилась: перезапусти PowerMill — он читает файл "
                "настройки при старте."
            )
    return result


def save_report(result: RibbonResult) -> Path:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(result.format(), encoding="utf-8")
    return REPORT_FILE

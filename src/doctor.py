"""
Проверка, готов ли компьютер к работе (пункт 40).

Зачем
-----
«Поставил и не работает» — самая частая беда любой программы на Windows. Поэтому
здесь один сценарий, который проходит по всем узлам и **прямо говорит**, что в
порядке, что нет и что делать. Он ничего не меняет: только смотрит и пишет отчёт.

Что проверяется
---------------
1. Windows и версия Python (нужен 3.10+);
2. виртуальное окружение и ключевые библиотеки;
3. папки данных (правило проекта: тяжёлое — на диск E:, либо папка, выбранная
   при установке);
4. PowerMill: установлен ли, есть ли COM-регистрация, запущен ли сейчас;
5. макросы PowerMill AI: записаны ли в папку макросов PowerMill (пункты 23, 28);
6. лента (пункт 34) и плагин (пункт 38): в каком состоянии;
7. Ollama / ключ API — какой «мозг» доступен (локальный или облачный);
8. справка PowerMill: разобрана ли (пункты 2–4).

Результат: отчёт `output\\doctor_report.txt` со списком ✔/✘ и понятными советами.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from config import (CHROMA_DIR, DATA_ROOT, HELP_DIR, OUTPUT_DIR,
                    PYTHON_MIN, PYTHON_MAX)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_FILE = OUTPUT_DIR / "doctor_report.txt"

# Ключевые библиотеки: без них ассистент не работает (остальное — по желанию)
REQUIRED_MODULES = {
    "requests": "обмен с ИИ по API",
    "bs4": "разбор страниц справки",
    "lxml": "ускоренный разбор справки",
}
OPTIONAL_MODULES = {
    "psutil": "поиск запущенных процессов PowerMill (пункт 23)",
    "win32com": "мост к PowerMill через COM (пункты 24, 31, 33)",
    "chromadb": "векторный поиск по справке (пункт 6)",
    "sentence_transformers": "смысловой поиск (пункт 6)",
    "faster_whisper": "разбор видео (по желанию)",
}

STATUS_OK = "ok"
STATUS_BAD = "bad"
STATUS_WARN = "warn"
STATUS_SKIP = "skip"


@dataclass
class Check:
    """Один пункт проверки."""

    title: str
    status: str
    detail: str = ""
    advice: str = ""

    @property
    def mark(self) -> str:
        return {"ok": "✔", "bad": "✘", "warn": "•", "skip": "—"}.get(self.status, "?")


@dataclass
class DoctorReport:
    """Весь результат проверки."""

    checks: list[Check] = field(default_factory=list)

    def add(self, title: str, status: str, detail: str = "", advice: str = "") -> Check:
        check = Check(title, status, detail, advice)
        self.checks.append(check)
        return check

    @property
    def problems(self) -> list[Check]:
        return [check for check in self.checks if check.status == STATUS_BAD]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.status == STATUS_WARN]

    @property
    def ready(self) -> bool:
        return not self.problems

    def format(self) -> str:
        lines = [
            "PowerMill AI — проверка компьютера (пункт 40)",
            time.strftime("Проверено: %d.%m.%Y %H:%M"),
            f"Python: {sys.version.split()[0]} ({sys.executable})",
            "",
            "=" * 62,
        ]
        for check in self.checks:
            lines.append(f"  {check.mark} {check.title}"
                         + (f" — {check.detail}" if check.detail else ""))
            if check.advice and check.status in (STATUS_BAD, STATUS_WARN):
                for part in check.advice.splitlines():
                    lines.append(f"      {part}")
        lines.append("=" * 62)
        lines.append("")
        if self.ready:
            lines.append("ИТОГ: компьютер готов. Ошибок нет.")
        else:
            lines.append(f"ИТОГ: не готово — ошибок {len(self.problems)}:")
            for check in self.problems:
                lines.append(f"  ✘ {check.title}: {check.detail}")
        if self.warnings:
            lines.append("")
            lines.append("На что посмотреть (не мешает работе):")
            for check in self.warnings:
                lines.append(f"  • {check.title}: {check.detail}")
        lines.append("")
        lines.append("Что делать дальше:")
        lines.append("  • ярлык «PowerMill AI» на рабочем столе — окно приложения;")
        lines.append("  • в PowerMill: вкладка «PowerMill AI» (пункт 34) или панель "
                     "плагина (пункт 38);")
        lines.append("  • все отчёты: start_menu.bat -> 29.")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Отдельные проверки (каждую можно вызвать и по одной)
# --------------------------------------------------------------------------
def check_python() -> Check:
    version = sys.version_info
    text = ".".join(str(part) for part in version[:3])
    if version < PYTHON_MIN:
        return Check("Python", STATUS_BAD, text,
                     f"Нужен Python {'.'.join(map(str, PYTHON_MIN))} или новее. "
                     "Скачай с python.org (галочка «Add to PATH») и запусти "
                     "install.bat заново.")
    if version >= PYTHON_MAX:
        return Check("Python", STATUS_WARN, text,
                     "Очень новая версия: часть библиотек может ставиться дольше. "
                     "Если что-то не ставится — возьми Python 3.12.")
    return Check("Python", STATUS_OK, text)


def check_venv(project_dir: Path | str = PROJECT_ROOT) -> Check:
    root = Path(project_dir)
    for candidate in (root / ".venv" / "Scripts" / "python.exe",
                      root / "venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return Check("Виртуальное окружение", STATUS_OK, str(candidate))
    return Check("Виртуальное окружение", STATUS_WARN,
                 "не найдено — работаем системным Python",
                 "Запусти install.bat (он создаст .venv и поставит библиотеки).")


def check_modules() -> list[Check]:
    checks: list[Check] = []
    for name, purpose in REQUIRED_MODULES.items():
        if importlib.util.find_spec(name) is not None:
            checks.append(Check(f"Библиотека {name}", STATUS_OK, purpose))
        else:
            checks.append(Check(f"Библиотека {name}", STATUS_BAD, f"нет ({purpose})",
                                "Запусти install.bat — он поставит нужное."))
    missing = [name for name in OPTIONAL_MODULES
               if importlib.util.find_spec(name) is None]
    if missing:
        checks.append(Check("Библиотеки по желанию", STATUS_WARN,
                            "нет: " + ", ".join(missing),
                            "Без них недоступны: " + "; ".join(
                                OPTIONAL_MODULES[n] for n in missing)))
    else:
        checks.append(Check("Библиотеки по желанию", STATUS_OK, "все на месте"))
    return checks


def check_data_root(data_root: Path | str = DATA_ROOT) -> Check:
    import config

    notes = list(getattr(config, "DATA_ROOT_NOTE", []))
    root = Path(data_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".doctor_probe"
        probe.write_text("ок", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return Check("Папка данных", STATUS_BAD, f"{root} ({error})",
                     "Выбери другую папку: запусти install.bat и укажи путь, "
                     "например D:\\powermill-ai.")
    size_hint = ""
    try:
        usage = shutil.disk_usage(root)
        size_hint = f", свободно {usage.free / 1024 ** 3:.0f} ГБ"
    except OSError:
        pass
    if notes:
        # Папку пришлось взять другую (например, диска E: нет) — говорим прямо
        # и подсказываем, как выбрать свою.
        return Check("Папка данных", STATUS_WARN, f"{root}{size_hint}",
                     "\n".join(notes) + "\nВыбрать другую: кнопка «Папка данных…» "
                     "в окне приложения или install.bat.")
    return Check("Папка данных", STATUS_OK, f"{root}{size_hint}")


def check_chroma() -> Check:
    folder = Path(CHROMA_DIR)
    if not folder.exists():
        return Check("Векторная база (ChromaDB)", STATUS_WARN, "папки нет",
                     "Собери пунктом 6 меню (долго, лучше ночью) — тогда /ask "
                     "будет искать по всему объёму справки.")
    files = list(folder.glob("**/*"))
    if not files:
        return Check("Векторная база (ChromaDB)", STATUS_WARN, "папка пустая",
                     "Собери пунктом 6 меню.")
    return Check("Векторная база (ChromaDB)", STATUS_OK,
                 f"{len(files)} файлов в {folder}")


def check_help_parsed(data_root: Path | str = DATA_ROOT) -> Check:
    db = Path(data_root) / "help_search.db"
    if db.exists():
        return Check("Справка разобрана (поиск)", STATUS_OK,
                     f"{db} ({db.stat().st_size / 1024 ** 2:.1f} МБ)")
    return Check("Справка разобрана (поиск)", STATUS_WARN, "базы поиска нет",
                 "Запусти пункт 4 меню (разбор справки) — он долгий, лучше ночью.")


def check_help_dir() -> Check:
    folder = Path(HELP_DIR)
    if folder.exists():
        return Check("Папка справки PowerMill", STATUS_OK, str(folder))
    return Check("Папка справки PowerMill", STATUS_WARN, f"нет: {folder}",
                 "Если PowerMill установлен в другое место — задай путь "
                 "переменной POWERMILL_HELP_DIR.")


def check_powermill_installed() -> Check:
    from src import power_mill_link

    found = power_mill_link.find_install_dirs()
    if not found:
        return Check("PowerMill установлен", STATUS_BAD, "не найден",
                     "Этот ассистент работает вместе с PowerMill. Установи "
                     "PowerMill и запусти проверку снова.")
    return Check("PowerMill установлен", STATUS_OK,
                 "; ".join(str(path) for path in found[:3]))


def check_powermill_running() -> Check:
    from src import pm_com

    session, message = pm_com.connect()
    if session is None:
        return Check("PowerMill запущен и отвечает", STATUS_WARN, message,
                     "Открой PowerMill с проектом — тогда работают пункты 24, "
                     "31, 33, 35, 36, 37.")
    try:
        counts = session.counts()
        detail = (f"версия {session.version}; инструментов {counts.get('tools', 0)}, "
                  f"траекторий {counts.get('toolpaths', 0)}")
    except Exception:                                          # noqa: BLE001
        detail = f"версия {session.version}"
    if session.version and "неизвестна" not in session.version:
        return Check("PowerMill запущен и отвечает", STATUS_OK, detail)
    return Check("PowerMill запущен и отвечает", STATUS_WARN, detail, "Проверь мост "
                 "(пункт 27 ставит pywin32).")


def check_macros() -> Check:
    from src import pm_macro

    folder = pm_macro.MACRO_DIR
    if not folder.exists():
        return Check("Макросы PowerMill AI", STATUS_WARN, "не созданы",
                     "Запусти пункт 28 — он запишет макросы и скопирует их в "
                     "папку макросов PowerMill.")
    macros = sorted(folder.glob("PM_AI_*.mac"))
    if not macros:
        return Check("Макросы PowerMill AI", STATUS_WARN, "нет файлов PM_AI_*.mac",
                     "Запусти пункт 28.")
    power_mill = pm_macro.power_mill_macro_folders()
    if not power_mill:
        return Check("Макросы PowerMill AI", STATUS_WARN,
                     f"{len(macros)} макросов, но папка PowerMill не найдена",
                     "Добавь путь в PowerMill: Макрос -> Пути макросов.")
    return Check("Макросы PowerMill AI", STATUS_OK,
                 f"{len(macros)} макросов, папка PowerMill: {power_mill[0]}")


def check_ribbon() -> Check:
    from src import pm_ribbon

    folder = pm_ribbon.find_ribbon_file()
    if folder is None:
        return Check("Вкладка на ленте PowerMill (пункт 34)", STATUS_WARN,
                     "настройка ленты ещё не создавалась",
                     "Открой в PowerMill: Файл -> Параметры -> Настройка ленты, "
                     "закрой ОК и запусти пункт 34.")
    text = pm_ribbon.REPORT_FILE
    if text.exists() and "PowerMill AI" in text.read_text(encoding="utf-8",
                                                          errors="replace"):
        return Check("Вкладка на ленте PowerMill (пункт 34)", STATUS_OK,
                     str(folder))
    return Check("Вкладка на ленте PowerMill (пункт 34)", STATUS_WARN,
                 f"файл есть ({folder}), но вкладка не ставилась",
                 "Запусти пункт 34 — он добавит вкладку «PowerMill AI».")


def check_plugin() -> Check:
    from src import pm_plugin

    dll = pm_plugin.dll_path()
    report = pm_plugin.REPORT_FILE
    if dll.exists():
        return Check("Плагин-панель (пункт 38)", STATUS_OK,
                     f"собран: {dll}")
    if report.exists():
        text = report.read_text(encoding="utf-8", errors="replace")
        first = next((line.strip() for line in text.splitlines()
                      if line.strip().startswith("✘")), "")
        return Check("Плагин-панель (пункт 38)", STATUS_WARN,
                     "ещё не собран", first or "Запусти пункт 38 (нужен пункт 25).")
    return Check("Плагин-панель (пункт 38)", STATUS_SKIP,
                 "не собирался (это не обязательно — есть лента и окно)")


def check_brain() -> list[Check]:
    """Чем ассистент думает: облачный ключ или локальная модель."""
    checks: list[Check] = []
    key_file = Path(DATA_ROOT) / "api_key.json"
    has_key = key_file.exists()
    ollama = shutil.which("ollama")
    if has_key:
        checks.append(Check("ИИ по API", STATUS_OK, f"ключ найден: {key_file}"))
    else:
        checks.append(Check("ИИ по API", STATUS_SKIP, "ключа нет (не обязательно)",
                            "Пункт 21 меню — вставить ключ, если хочешь облачный ИИ."))
    if ollama:
        checks.append(Check("Локальный ИИ (Ollama)", STATUS_OK, ollama))
    else:
        checks.append(Check("Локальный ИИ (Ollama)", STATUS_WARN,
                            "ollama не найдена в PATH",
                            "Без неё и без ключа работает только поиск и "
                            "калькулятор режимов. Поставь Ollama (ollama.com)."))
    return checks


def check_ui(project_dir: Path | str = PROJECT_ROOT) -> Check:
    """Может ли открыться окно приложения: нужен tkinter и иконка."""
    if importlib.util.find_spec("tkinter") is None:
        return Check("Окно приложения (пункт 39)", STATUS_BAD, "нет модуля tkinter",
                     "Python поставлен без Tcl/Tk. Переустанови Python с сайта "
                     "python.org и не снимай галочку «tcl/tk and IDLE» — или "
                     "работай через start_menu.bat.")
    icon = Path(project_dir) / "assets" / "app.ico"
    if not icon.exists():
        return Check("Окно приложения (пункт 39)", STATUS_WARN,
                     "tkinter есть, иконки нет",
                     "Иконка — только украшение; положи assets\\app.ico, если "
                     "хочешь её вернуть.")
    return Check("Окно приложения (пункт 39)", STATUS_OK,
                 f"tkinter есть, иконка {icon.name}")


def check_install_settings(project_dir: Path | str = PROJECT_ROOT,
                           data_root: Path | str = DATA_ROOT) -> Check:
    """Записана ли настройка установки (install.json) — от неё зависят папки."""
    settings = Path(project_dir) / "install.json"
    if settings.exists():
        return Check("Настройка установки", STATUS_OK, str(settings))
    return Check("Настройка установки", STATUS_WARN, "install.json нет",
                 "Запусти install.bat — он запишет папку данных в install.json, "
                 "и программа перестанет зависеть от переменных окружения.")


def check_tests(project_dir: Path | str = PROJECT_ROOT) -> Check:
    folder = Path(project_dir) / "tests"
    if not folder.exists():
        return Check("Тесты проекта", STATUS_SKIP, "папки tests нет")
    count = len(list(folder.glob("test_*.py")))
    return Check("Тесты проекта", STATUS_OK,
                 f"{count} файлов тестов (запуск: run_tests.bat)")


def collect(data_root: Path | str = DATA_ROOT,
            project_dir: Path | str = PROJECT_ROOT,
            include_powermill: bool = True) -> DoctorReport:
    """Проходит все проверки и возвращает отчёт."""
    report = DoctorReport()
    report.checks.append(check_python())
    report.checks.append(Check("Система", STATUS_OK,
                               f"{platform.system()} {platform.release()}"))
    report.checks.append(check_venv(project_dir))
    report.checks.extend(check_modules())
    report.checks.append(check_data_root(data_root))
    report.checks.append(check_help_dir())
    report.checks.append(check_help_parsed(data_root))
    report.checks.append(check_chroma())
    if include_powermill:
        report.checks.append(check_powermill_installed())
        report.checks.append(check_powermill_running())
        report.checks.append(check_macros())
        report.checks.append(check_ribbon())
        report.checks.append(check_plugin())
    report.checks.extend(check_brain())
    report.checks.append(check_ui(project_dir))
    report.checks.append(check_install_settings(project_dir, data_root))
    report.checks.append(check_tests(project_dir))
    return report


def save(report: DoctorReport, path: Path | str = REPORT_FILE) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.format(), encoding="utf-8")
    return target


def quick_summary(report: DoctorReport) -> str:
    """Короткая строка для окна приложения."""
    if report.ready:
        return "Проверка компьютера: всё в порядке"
    return (f"Проверка компьютера: ошибок {len(report.problems)}, "
            f"предупреждений {len(report.warnings)}")

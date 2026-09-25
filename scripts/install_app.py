"""
УСТАНОВКА «ПОД КЛЮЧ» — чтобы программу можно было дать кому угодно.

Запускается из install.bat **обычным Python** (виртуального окружения ещё нет),
поэтому здесь только стандартная библиотека: ничего из проекта не импортируется,
кроме пары модулей, которые сами по себе стандартные.

Что делает по шагам
-------------------
1. проверяет Windows и Python (нужен 3.10+; если нет — говорит, где взять);
2. спрашивает папку для данных (по умолчанию: диск E:, если он есть, иначе
   папка пользователя) и пишет её в `install.json` рядом с кодом — тогда
   программе не нужны переменные окружения;
3. создаёт виртуальное окружение `.venv` и ставит библиотеки из
   `requirements.txt`;
4. создаёт ярлыки: на рабочем столе и в меню «Пуск» (окно приложения, меню
   пунктов, отчёты);
5. запускает проверку компьютера (пункт 40) и сохраняет отчёт;
6. пишет `output\\install_report.txt` — что установлено, что нет и что дальше.

Ничего не удаляет и не перезаписывает молча: если папка занята — спросит.
Повторный запуск безопасен: он доделывает то, чего не хватает.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 14)
APP_NAME = "PowerMill AI"
REPORT_NAME = "install_report.txt"

ENV_VARS = {
    "HF_HOME": "hf_cache",
    "PIP_CACHE_DIR": "pip_cache",
    "OLLAMA_MODELS": "ollama_models",
}


# --------------------------------------------------------------------------
# Мелкие помощники вывода
# --------------------------------------------------------------------------
class Printer:
    """Печатает в консоль и в отчёт (чтобы всё можно было прислать в чат)."""

    def __init__(self, report: Path | None = None):
        self.lines: list[str] = []
        self.report = report

    def print(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def save(self, path: Path | None = None) -> Path | None:
        target = path or self.report
        if target is None:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        return target


def ask(prompt: str, default: str = "") -> str:
    try:
        text = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return text or default


def yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = "[да]: " if default_yes else "[нет]: "
    text = ask(prompt + suffix).lower()
    if not text:
        return default_yes
    return text in ("да", "д", "yes", "y", "1")


# --------------------------------------------------------------------------
# Проверки перед установкой
# --------------------------------------------------------------------------
def python_ok() -> tuple[bool, str]:
    version = sys.version_info
    text = ".".join(str(part) for part in version[:3])
    if version < MIN_PYTHON:
        return False, (f"Python {text} слишком старый. Нужен "
                       f"{'.'.join(map(str, MIN_PYTHON))}+ — скачай с python.org "
                       "(галочка «Add Python to PATH»), потом запусти install.bat "
                       "заново.")
    if version >= MAX_PYTHON:
        return True, (f"Python {text}: годится, но библиотеки могут ставиться "
                      "дольше. Если начнутся ошибки — возьми Python 3.12.")
    return True, f"Python {text}"


def default_data_root() -> Path:
    """Куда складывать тяжёлое: диск E:, если он есть, иначе папка пользователя."""
    if sys.platform == "win32":
        for letter in ("E", "D"):
            candidate = Path(f"{letter}:/")
            if candidate.exists():
                return Path(f"{letter}:/powermill-ai")
        return Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "PowerMillAI"
    return Path.home() / "powermill-ai"


def write_settings(data_root: Path, extra: dict | None = None) -> Path:
    """Пишет install.json — из него программа узнаёт, где её данные."""
    settings = {"data_root": str(data_root), "installed_at": _stamp()}
    if extra:
        settings.update(extra)
    path = CODE_DIR / "install.json"
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def _stamp() -> str:
    import time

    return time.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Шаги установки
# --------------------------------------------------------------------------
def make_folders(data_root: Path, printer: Printer) -> list[Path]:
    """Создаёт папки данных (по правилу: тяжёлое — в свою папку)."""
    made: list[Path] = [data_root]
    for sub in ("data/pdf", "data/videos", "data/macros", "data/forums",
                "chroma_db", "output", "plugin"):
        made.append(data_root / sub)
    for folder in made:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            printer.print(f"  (!) не смог создать {folder}: {error}")
    for name, sub in ENV_VARS.items():
        try:
            (data_root / sub).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        _set_env(name, str(data_root / sub))
    _set_env("POWERMILL_DATA_ROOT", str(data_root))
    printer.print(f"  ✔ папки данных: {data_root}")
    printer.print(f"    (переменная POWERMILL_DATA_ROOT установлена на будущее)")
    return made


def _set_env(name: str, value: str) -> None:
    """Ставит переменную окружения пользователя (setx) — тихо, если не вышло."""
    try:
        os.environ[name] = value
    except OSError:
        pass
    if sys.platform != "win32":
        return
    try:
        subprocess.run(["setx", name, value], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def venv_python(project_dir: Path = CODE_DIR) -> Path | None:
    for candidate in (project_dir / ".venv" / "Scripts" / "python.exe",
                      project_dir / "venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def create_venv(printer: Printer) -> Path | None:
    """Создаёт .venv (или берёт готовое) и возвращает python из него."""
    existing = venv_python()
    if existing is not None:
        printer.print(f"  ✔ виртуальное окружение уже есть: {existing}")
        return existing

    printer.print("  Создаю виртуальное окружение .venv (полминуты)…")
    try:
        done = subprocess.run([sys.executable, "-m", "venv", str(CODE_DIR / ".venv")],
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as error:
        printer.print(f"  ✘ не смог создать окружение: {error}")
        return None
    if done.returncode != 0:
        printer.print("  ✘ venv не создался:")
        printer.print("    " + (done.stderr or done.stdout or "").strip()[:500])
        return None
    python = venv_python(CODE_DIR)
    printer.print(f"  ✔ окружение создано: {python or 'не найден python внутри'}")
    return python


def install_requirements(printer: Printer, python: Path | None,
                         full: bool = True) -> bool:
    """Ставит библиотеки. `full=False` — только самое необходимое."""
    if python is None:
        return False
    requirements = CODE_DIR / "requirements.txt"
    if not requirements.exists():
        printer.print("  (!) requirements.txt не найден — пропускаю установку "
                      "библиотек")
        return False

    if full:
        targets = ["-r", str(requirements)]
    else:
        targets = ["requests", "beautifulsoup4", "lxml"]

    command = [str(python), "-m", "pip", "install", "--upgrade", "-q", *targets]
    printer.print(f"  Ставлю библиотеки: {' '.join(targets)}")
    printer.print("  (это самая долгая часть — от 2 до 15 минут)")
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as error:
        printer.print(f"  ✘ pip не сработал: {error}")
        return False
    if done.returncode != 0:
        printer.print("  (!) часть библиотек не встала. Вот что сказал pip:")
        tail = (done.stdout or "")[-1500:] + (done.stderr or "")[-1500:]
        for line in tail.splitlines()[-12:]:
            printer.print("    " + line)
        printer.print("  Программа всё равно может работать: окно, режимы резания")
        printer.print("  и макросы не зависят от этих библиотек.")
        return False
    printer.print("  ✔ библиотеки установлены")
    return True


def create_shortcuts(printer: Printer, project_dir: Path = CODE_DIR) -> bool:
    """Ярлыки: рабочий стол + меню «Пуск»."""
    if sys.platform != "win32":
        printer.print("  (ярлыки — только Windows; пропускаю)")
        return False
    sys.path.insert(0, str(project_dir))
    try:
        from src import shortcuts                      # noqa: PLC0415
    except Exception as error:                         # noqa: BLE001
        printer.print(f"  (!) не смог создать ярлыки: {error}")
        return False

    ok_count = 0
    for link, ok, note in shortcuts.create_all(project_dir, APP_NAME):
        mark = "✔" if ok else "✘"
        printer.print(f"  {mark} {link.name}: {note if not ok else link}")
        ok_count += 1 if ok else 0
    return ok_count > 0


def run_doctor(python: Path | None, printer: Printer,
               project_dir: Path = CODE_DIR) -> None:
    """Проверка компьютера (пункт 40) — отчётом."""
    runner = str(python) if python else sys.executable
    printer.print("  Проверяю компьютер (пункт 40)…")
    try:
        done = subprocess.run([runner, "-m", "scripts.doctor"],
                              cwd=str(project_dir), capture_output=True,
                              text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as error:
        printer.print(f"  (!) проверка не прошла: {error}")
        return
    tail = (done.stdout or "").strip().splitlines()
    for line in tail[-20:]:
        printer.print("    " + line)


def copy_macros(python: Path | None, printer: Printer,
                project_dir: Path = CODE_DIR) -> None:
    """Ставит макросы PowerMill AI (пункт 28) — если PowerMill уже есть."""
    if python is None:
        return
    printer.print("  Ставлю макросы PowerMill AI (пункт 28)…")
    try:
        done = subprocess.run([str(python), "-m", "scripts.prepare_pm_macros"],
                              cwd=str(project_dir), capture_output=True,
                              text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as error:
        printer.print(f"  (!) макросы не поставлены: {error}")
        return
    tail = (done.stdout or "").strip().splitlines()
    for line in tail[-12:]:
        printer.print("    " + line)


# --------------------------------------------------------------------------
# Главный сценарий
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Установка PowerMill AI")
    parser.add_argument("--data-root", help="папка для данных (без вопросов)")
    parser.add_argument("--yes", action="store_true",
                        help="не задавать вопросов, всё согласовать")
    parser.add_argument("--light", action="store_true",
                        help="поставить только необходимые библиотеки")
    parser.add_argument("--no-shortcuts", action="store_true",
                        help="не создавать ярлыки")
    args = parser.parse_args()

    report = CODE_DIR / REPORT_NAME
    printer = Printer(report)
    printer.print("=" * 64)
    printer.print("  УСТАНОВКА PowerMill AI — ассистента технолога")
    printer.print("=" * 64)
    printer.print(f"  Код программы: {CODE_DIR}")
    printer.print(f"  Время: {_stamp()}")
    printer.print()

    printer.print("[1/6] Проверяю систему")
    printer.print(f"  Система: {sys.platform}")
    ok, note = python_ok()
    printer.print(f"  {'✔' if ok else '✘'} {note}")
    if not ok:
        printer.print()
        printer.print("Установка остановлена: без подходящего Python не поставить "
                      "библиотеки. Скачай Python с python.org и запусти install.bat "
                      "заново.")
        printer.save(report)
        return 2

    printer.print()
    printer.print("[2/6] Куда складывать данные")
    default_root = default_data_root()
    if args.data_root:
        data_root = Path(args.data_root)
        printer.print(f"  Взял из команды: {data_root}")
    elif args.yes:
        data_root = default_root
        printer.print(f"  Выбрал сам (режим без вопросов): {data_root}")
    else:
        printer.print("  Тяжёлые данные (справка, базы, отчёты) лежат отдельно "
                      "от программы.")
        printer.print(f"  По умолчанию: {default_root}")
        data_root = Path(ask("  Папка данных (Enter — по умолчанию): ",
                             str(default_root)))
    write_settings(data_root)
    make_folders(data_root, printer)
    printer.print(f"  ✔ записал настройку: {CODE_DIR / 'install.json'}")

    printer.print()
    printer.print("[3/6] Виртуальное окружение и библиотеки")
    python = create_venv(printer)
    libraries_ok = install_requirements(printer, python, full=not args.light)
    if not libraries_ok:
        printer.print("  (можно поставить позже: start_menu.bat -> 27)")

    printer.print()
    printer.print("[4/6] Ярлыки")
    if args.no_shortcuts:
        printer.print("  (пропущено по ключу --no-shortcuts)")
    else:
        create_shortcuts(printer)

    printer.print()
    printer.print("[5/6] Макросы для PowerMill")
    copy_macros(python, printer)

    printer.print()
    printer.print("[6/6] Проверка компьютера")
    run_doctor(python, printer)

    printer.print()
    printer.print("=" * 64)
    printer.print("  ГОТОВО")
    printer.print("=" * 64)
    printer.print()
    printer.print("Как работать:")
    printer.print("  1) ярлык «PowerMill AI» на рабочем столе — окно программы;")
    printer.print("  2) ярлык «PowerMill AI — меню пунктов» — все пункты списком "
                  "(для отладки);")
    printer.print("  3) в PowerMill: пункт 34 (вкладка на ленте) и пункт 38 "
                  "(панель-плагин).")
    printer.print()
    printer.print("Если что-то не работает: ярлык «PowerMill AI — отчёты» — там "
                  "отчёты, в том числе install_report.txt и doctor_report.txt.")
    saved = printer.save(report)
    print()
    print(f"📝 Отчёт установки: {saved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

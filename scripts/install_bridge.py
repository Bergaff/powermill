"""
Мост Python ↔ PowerMill (пункт 27 меню).

Что делает:
1. ставит в venv два моста:
   * **pywin32** — связь с PowerMill как с COM-сервером (самый надёжный путь,
     у тебя PowerMill уже зарегистрирован в системе);
   * **pythonnet** — связь через официальные .NET-сборки
     `Delcam.ProductInterface.PowerMILL.dll` (они найдены у тебя в
     PowerMill Project Server 2026);
2. проверяет, что они импортируются;
3. сразу пробует подключиться к запущенному PowerMill и печатает разведку API
   (`src/pm_probe.py`): какие методы есть, как называется активный проект,
   что читается из коллекций.

Ничего в PowerMill не меняется: только чтение и одна безвредная команда
`PRINT "POWERMILL AI TEST OK"`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.applog import start_log                     # noqa: E402

PACKAGES = [
    ("pywin32", "связь через COM (PowerMill.Application)"),
    ("pythonnet", "связь через .NET-сборки Autodesk"),
]


def python_exe() -> str:
    """Интерпретатор, в который ставим пакеты (venv, если он есть)."""
    venv_python = Path(sys.executable)
    return str(venv_python)


def pip_install(package: str) -> tuple[bool, str]:
    """Ставит пакет в текущее окружение. Возвращает (успех, вывод)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", package],
            capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return False, "таймаут установки (нет интернета или медленно)"
    except Exception as error:  # noqa: BLE001
        return False, f"{type(error).__name__}: {error}"

    if result.returncode == 0:
        return True, "установлено"
    tail = (result.stderr or result.stdout or "").strip().splitlines()
    return False, " | ".join(tail[-3:]) if tail else "неизвестная ошибка"


def check_import(module: str) -> tuple[bool, str]:
    """Проверяет импорт в ДОЧЕРНЕМ процессе — чтобы подхватился свежий пакет."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}; print('import ok')"],
            capture_output=True, text=True, timeout=120)
    except Exception as error:  # noqa: BLE001
        return False, f"{type(error).__name__}: {error}"
    if result.returncode == 0:
        return True, "import ok"
    tail = (result.stderr or "").strip().splitlines()
    return False, tail[-1] if tail else "импорт не прошёл"


def main() -> int:
    log = start_log("install_bridge")

    print("=" * 60)
    print("  МОСТ PYTHON ↔ PowerMill")
    print("  Ставлю: pywin32 (COM) и pythonnet (.NET)")
    print("=" * 60)
    print()
    print(f"Python: {sys.executable}")
    print(f"Лог:    {log}")
    print()

    results: list[tuple[str, bool, str]] = []
    for package, purpose in PACKAGES:
        print(f"[{package}] {purpose}")
        ok, message = pip_install(package)
        print(f"    установка: {'OK' if ok else 'ОШИБКА'} — {message}")
        if ok:
            import_ok, import_message = check_import(package.replace("-", "_"))
            print(f"    импорт:    {'OK' if import_ok else 'ОШИБКА'} — {import_message}")
            results.append((package, import_ok, import_message))
        else:
            results.append((package, False, message))
        print()

    # что нашли из сборок и COM — по разведке
    from src import power_mill_link

    data = power_mill_link.collect()
    assemblies = data.get("assemblies") or {}
    progids = data.get("progids") or []
    print("Что видит система:")
    print(f"  COM-классы PowerMill: {', '.join(progids[:4]) if progids else 'нет'}")
    for name, places in list(assemblies.items())[:4]:
        print(f"  сборка API: {name}")
        print(f"      {places[0]}")
    print()

    good = [name for name, ok, _msg in results if ok]
    if not good:
        print("[!] Мосты не установились.")
        print("    Проверь интернет и повтори. Если ошибка про SSL/прокси —")
        print("    подготовь отчёт (пункт 13 меню) и пришли в чат.")
        return 2

    print(f"[OK] Работает: {', '.join(good)}")

    # запускаем разведку API прямо сейчас
    print()
    print("=" * 60)
    print("  ПРОБУЮ ПОДКЛЮЧИТЬСЯ К PowerMill")
    print("=" * 60)
    print()
    if data.get("running") is False:
        print("PowerMill сейчас не запущен.")
        print("  Запусти PowerMill с проектом и повтори пункт 27 —")
        print("  тогда разведка покажет структуру API.")
        print()
        print("Что уже готово: мост стоит, дальше только открыть PowerMill.")
        return 0

    from src import pm_probe

    return pm_probe.run()


if __name__ == "__main__":
    sys.exit(main())

"""
Мост Python ↔ PowerMill (пункт 27 меню).

Что делает:
1. ставит в окружение два моста:
   * **pywin32** — связь с PowerMill как с COM-сервером (самый надёжный путь,
     PowerMill уже зарегистрирован в системе);
   * **pythonnet** — связь через официальные .NET-сборки
     `Delcam.ProductInterface.PowerMILL.dll`;
2. проверяет, что они импортируются (в дочернем процессе — чтобы подхватился
   только что установленный пакет);
3. пишет отчёт `output\\pm_api_probe.txt` со всем, что видит система, и — если
   PowerMill запущен — делает разведку API (какие методы, как называется
   активный проект, что читается из коллекций).

Ничего в PowerMill не меняется: только чтение и одна безвредная команда
`PRINT "POWERMILL AI TEST OK"`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.applog import start_log                     # noqa: E402

# Пакет -> (что даёт, какие модули должны импортироваться)
#
# Важно: пакет pywin32 ставит модули win32com/pythoncom, а модуля с именем
# «pywin32» не существует. Раньше проверка шла по имени пакета и врала:
# «импорт: ОШИБКА — No module named 'pywin32'» при живом pywin32.
PACKAGES: list[tuple[str, str, tuple[str, ...]]] = [
    ("pywin32", "связь через COM (PowerMill.Application)",
     ("win32com.client", "pythoncom")),
    ("pythonnet", "связь через .NET-сборки Autodesk", ("clr",)),
]


def python_exe() -> str:
    """Интерпретатор, в который ставим пакеты (тот, что запустил батник/venv)."""
    return sys.executable


def pip_install(package: str) -> tuple[bool, str]:
    """Ставит пакет в текущее окружение. Возвращает (успех, вывод)."""
    try:
        result = subprocess.run(
            [python_exe(), "-m", "pip", "install", "--quiet", package],
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
            [python_exe(), "-c", f"import {module}; print('import ok')"],
            capture_output=True, text=True, timeout=120)
    except Exception as error:  # noqa: BLE001
        return False, f"{type(error).__name__}: {error}"
    if result.returncode == 0:
        return True, "import ok"
    tail = (result.stderr or "").strip().splitlines()
    return False, tail[-1] if tail else "импорт не прошёл"


def check_package(modules: tuple[str, ...]) -> tuple[bool, str]:
    """Проверяет модули пакета: достаточно первого рабочего."""
    errors: list[str] = []
    for module in modules:
        ok, message = check_import(module)
        if ok:
            return True, f"import ok ({module})"
        errors.append(f"{module}: {message}")
    return False, "; ".join(errors)


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
    for package, purpose, modules in PACKAGES:
        print(f"[{package}] {purpose}")
        ok, message = pip_install(package)
        print(f"    установка: {'OK' if ok else 'ОШИБКА'} — {message}")
        if ok:
            import_ok, import_message = check_package(modules)
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

    # --- отчёт: пишется ВСЕГДА, даже если PowerMill ещё не открыт -----------
    from src import pm_probe

    if data.get("running") is False:
        print()
        print("Проверяю подключение (PowerMill сейчас не запущен — это нормально).")
        print()
        pm_probe.run()                    # печатает и сохраняет отчёт
        print()
        print("=" * 60)
        print("  ЧТО ДЕЛАТЬ ДАЛЬШЕ")
        print("=" * 60)
        print()
        print("1. Запусти PowerMill и открой проект.")
        print("2. Снова запусти пункт 27 — тогда разведка покажет живой API.")
        print("   (мост уже стоит, заново ничего не устанавливается)")
        print()
        print(f"Отчёт сохранён: {pm_probe.PROBE_FILE}")
        print("Открыть его можно пунктом 29 меню («Показать отчёты»).")
        return 0

    print()
    print("=" * 60)
    print("  ПРОБУЮ ПОДКЛЮЧИТЬСЯ К PowerMill")
    print("=" * 60)
    print()
    rc = pm_probe.run()
    print()
    print(f"Отчёт сохранён: {pm_probe.PROBE_FILE}")
    print("Открыть его можно пунктом 29 меню («Показать отчёты»).")
    return rc


if __name__ == "__main__":
    sys.exit(main())

"""
СБОРКА И РЕГИСТРАЦИЯ ПЛАГИНА-ПАНЕЛИ (пункт 38 меню, шаг 2.3б).

Собирает панель «PowerMill AI» для PowerMill из исходника на C#:

1. показывает, что соберём (кнопки, каркас, компилятор, Python) — до сборки;
2. проверяет, всё ли на месте (csc.exe, Delcam.Plugins.Framework.dll, regasm.exe,
   Python проекта) и честно говорит, чего нет;
3. компилирует DLL тем же csc.exe, что в .NET Framework — Visual Studio не нужна;
4. по подтверждению регистрирует плагин (`regasm /register /codebase` + категория
   плагинов PowerMill в реестре — без неё PowerMill его не подхватит);
5. пишет отчёт `output\\pm_plugin_build_report.txt` и то, что НЕ проверено.

Запуск: scripts\\build_plugin.bat (или пункт 38 меню).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                        # noqa: E402
from src import plugin_scaffold, pm_plugin           # noqa: E402
from src.applog import start_log                     # noqa: E402
from src.console import Wizard, read_line            # noqa: E402

MANUAL_TEXT = """\
Если в PowerMill панели нет — проверь по шагам:
  1) PowerMill был запущен во время сборки? Перезапусти PowerMill.
  2) Пункт 25 находил каркас? Если Framework не найден, сборка ссылалась не на ту
     DLL — пришли output\\pm_plugin_build_report.txt и вывод консоли.
  3) Панель ищется в меню «Вид» -> «Панели» (Panes), называется «PowerMill AI».
     Если PowerMill при запуске ругается на плагин — отмени регистрацию:
     запусти этот пункт ещё раз и выбери «нет» на вопрос о сборке, а затем
     выполни в папке plugin\\PowerMillAI команду из register.bat с ключом /u
     (в отчёте есть готовый текст)."""


def ask_yes_no(prompt: str) -> bool | None:
    while True:
        text = read_line(prompt)
        if text is None:
            return None
        answer = (text or "").strip().lower()
        if answer in ("да", "д", "yes", "y", "1"):
            return True
        if answer in ("", "нет", "н", "no", "n", "0"):
            return False
        print("  Ответь «да» или «нет» (Enter — нет).")


def run(command: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Запускает команду и возвращает (код, весь вывод)."""
    try:
        done = subprocess.run(command, cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, timeout=600,
                              errors="replace")
    except FileNotFoundError:
        return 127, f"не нашёл программу: {command[0]}"
    except subprocess.TimeoutExpired:
        return 124, "команда не успела завершиться за 10 минут"
    except OSError as error:
        return 126, f"не смог запустить: {error}"
    output = (done.stdout or "") + (done.stderr or "")
    return done.returncode, output.strip()


def main() -> int:
    log = start_log("build_plugin")
    print("=" * 64)
    print("  ПУНКТ 38 — ПЛАГИН-ПАНЕЛЬ «PowerMill AI» (шаг 2.3б)")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print("  Собираю панель внутри PowerMill: кнопки сценариев и журнал.")
    print("  Кнопки — из того же списка, что на ленте (пункт 34): макросы")
    print("  выполняются прямо в PowerMill, сценарии с вопросами — отдельным окном.")
    print("  Visual Studio не нужна — компилятор берём из .NET Framework.")
    print()

    steps = [("Версия PowerMill для плагина",
              "какую версию писать в плагине (формат 2026.0)",
              pm_plugin.DEFAULT_PM_VERSION)]
    wizard = Wizard(steps)
    while not wizard.finished:
        print(wizard.prompt(), end="")
        text = read_line("")
        if text is None:
            return 0
        action = wizard.submit(text)
        if action == "menu":
            print("Ничего не менял.")
            return 0
        if action == "help":
            print("  Enter — значение по умолчанию, «назад» — предыдущий вопрос.")
        print()

    version = (wizard.answers[0] or pm_plugin.DEFAULT_PM_VERSION).strip()
    spec = pm_plugin.PluginSpec(
        pm_version=(version or pm_plugin.DEFAULT_PM_VERSION).strip(),
        python_exe=pm_plugin.python_exe(),
    )

    tools = plugin_scaffold.sdk_tools()
    references = pm_plugin.find_references()
    problems = pm_plugin.check_environment(tools, references, spec)

    print("=" * 64)
    print("  ЧТО СОБЕРЁМ (до сборки)")
    print("=" * 64)
    print("\n".join(pm_plugin.plan_lines(spec, tools, references)))
    print()

    if problems:
        print("  Сборка сейчас невозможна:")
        for problem in problems:
            print(f"    ✘ {problem}")
        print()
        print("  Что делать:")
        print("    • каркас нет — запусти пункт 25 (он копирует его из поставки);")
        print("    • csc.exe нет — он входит в .NET Framework 4.x, обычно уже в Windows;")
        print("    • Python нет — пункт 27 ставит пакеты в .venv проекта.")
        result = pm_plugin.format_result(problems, [], [], None)
        path = pm_plugin.report(problems, pm_plugin.plan_lines(spec, tools, references),
                                result, None)
        print()
        print(f"  Отчёт: {path} (пункт 29 меню)")
        return 1

    print("  Всё на месте. Собираю плагин…")
    print()
    source = pm_plugin.write_source(spec)
    print(f"  Исходник: {source}")

    code, output = run(pm_plugin.compile_command(spec, tools["csc.exe"], references),
                       cwd=pm_plugin.PROJECT_DIR)
    print(output or "(компилятор ничего не сказал)")
    print()

    errors, warnings = pm_plugin.parse_build_output(output)
    dll = pm_plugin.dll_path(spec.output_dir)
    built = code == 0 and dll.exists()

    result = pm_plugin.format_result([], errors, warnings, dll if dll.exists() else None)
    print(result)
    print()

    if not built:
        print("  Сборка не прошла. Пришли мне этот вывод — поправлю исходник.")
        path = pm_plugin.report([], pm_plugin.plan_lines(spec, tools, references),
                                result, None)
        print(f"  Отчёт: {path} (пункт 29 меню)")
        return 1

    print("=" * 64)
    print("  РЕГИСТРАЦИЯ В POWERMILL")
    print("=" * 64)
    print("  Без регистрации PowerMill плагин не увидит. Будут выполнены:")
    for command in pm_plugin.register_commands(spec, tools["regasm.exe"]):
        print(f"    • {' '.join(command)}")
    print()
    print("  Реестр и COM — вещи системные, поэтому спрашиваю отдельно.")
    print("  Если не хочешь менять систему — скажи «нет», собранная DLL останется.")
    print()

    answer = ask_yes_no("  Зарегистрировать плагин сейчас? (да/нет) [нет]: ")
    if not answer:
        print("Оставил без регистрации.")
        print("Позже: запусти этот пункт снова или выполни вручную "
              "(команды выше, нужны права администратора).")
        path = pm_plugin.report([], pm_plugin.plan_lines(spec, tools, references),
                                result + "\n\nРегистрация: отложена пользователем.", dll)
        print(f"  Отчёт: {path} (пункт 29 меню)")
        return 0

    registered = True
    for command in pm_plugin.register_commands(spec, tools["regasm.exe"]):
        code, output = run(command)
        mark = "ok" if code == 0 else f"код {code}"
        print(f"  [{mark}] {' '.join(command)}")
        if output:
            print("      " + output.replace("\n", "\n      ")[:1000])
        if code != 0 and "regasm" in command[0].lower():
            registered = False
    print()

    if registered:
        print("  ✔ Плагин зарегистрирован.")
        print("  Как посмотреть: перезапусти PowerMill -> меню «Вид» -> «Панели»")
        print("  (Panes) -> «PowerMill AI». Кнопки в панели — те же сценарии,")
        print("  что в пунктах 3, 31, 33, 35, 36, 37.")
    else:
        print("  (!) Регистрация не прошла — пришли вывод выше.")
    print()
    print(MANUAL_TEXT)
    print()

    result_all = result + ("\n\nРегистрация: выполнена." if registered
                           else "\n\nРегистрация: НЕ прошла (см. вывод выше).")
    path = pm_plugin.report([], pm_plugin.plan_lines(spec, tools, references),
                            result_all, dll)
    print(f"  Отчёт: {path} (пункт 29 меню)")
    return 0 if registered else 1


if __name__ == "__main__":
    sys.exit(main())

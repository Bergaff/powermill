"""
УДАЛЕНИЕ программы (ярлыки, регистрация плагина). Данные не трогает.

Запускается из uninstall.bat. Специально **не удаляет данные**: справку, базы и
отчёты человек мог собирать ночами, и терять их из-за «убери программу» нельзя.
Скрипт говорит, где они лежат, и предлагает удалить вручную, если точно нужно.

Что делает:
1. убирает ярлыки из меню «Пуск» и с рабочего стола;
2. отменяет регистрацию плагина (если он был собран) — regasm /unregister и
   запись категории в реестре;
3. пишет `output\\uninstall_report.txt`;
4. подсказывает, что осталось на диске (папка данных и venv).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

REPORT = CODE_DIR / "output" / "uninstall_report.txt"


def _load_data_root() -> Path | None:
    """Где данные — из install.json (или из настроек, если файл старый)."""
    path = CODE_DIR / "install.json"
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("data_root")
        if isinstance(value, str) and value.strip():
            return Path(value.strip())
    except (OSError, ValueError):
        pass
    return None


def remove_shortcuts(lines: list[str]) -> int:
    try:
        from src import shortcuts
    except Exception as error:                                    # noqa: BLE001
        lines.append(f"(!) ярлыки не удалить: {error}")
        return 0
    removed = shortcuts.remove_all()
    for link in removed:
        lines.append(f"✔ убран ярлык: {link}")
    if not removed:
        lines.append("• ярлыков не нашлось (уже убраны)")
    return len(removed)


def unregister_plugin(lines: list[str]) -> bool:
    """Отменяет регистрацию плагина, если он собран."""
    from src import pm_plugin

    dll = pm_plugin.dll_path()
    if not dll.exists():
        lines.append("• плагин не собран — отменять нечего")
        return False

    regasm = None
    try:
        from src import plugin_scaffold

        regasm = plugin_scaffold.sdk_tools().get("regasm.exe")
    except Exception:                                             # noqa: BLE001
        regasm = None
    if not regasm:
        lines.append("(!) regasm.exe не найден — отмени регистрацию вручную:")
        key = "{" + pm_plugin.PLUGIN_GUID + "}"
        lines.append(f"    regasm \"{dll}\" /unregister")
        for category in pm_plugin.PLUGIN_CATEGORY_GUIDS:
            lines.append(f"    reg delete \"HKCR\\CLSID\\{key}\\Implemented "
                         f"Categories\\{category}\" /f /reg:32 /reg:64")
        return False

    ok = True
    for command in pm_plugin.unregister_commands(pm_plugin.PluginSpec(), regasm):
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as error:
            lines.append(f"(!) {' '.join(command)}: {error}")
            ok = False
            continue
        state = "✔" if done.returncode == 0 else "•"
        lines.append(f"{state} {' '.join(command)}")
    return ok


def main() -> int:
    lines = [
        "PowerMill AI — удаление (ярлыки и регистрация плагина)",
    ]
    print("Убираю ярлыки…")
    count = remove_shortcuts(lines)
    print(f"  убрано ярлыков: {count}")

    print("Отменяю регистрацию плагина…")
    unregister_plugin(lines)

    data_root = _load_data_root()
    if data_root:
        size = ""
        try:
            total = sum(path.stat().st_size for path in data_root.rglob("*")
                        if path.is_file())
            size = f" ({total / 1024 ** 2:.0f} МБ)"
        except OSError:
            pass
        lines += [
            "",
            "Осталось на диске (это НЕ удаляю — вдруг понадобится):",
            f"  • данные и отчёты: {data_root}{size}",
            f"  • виртуальное окружение: {CODE_DIR / '.venv'}",
            f"  • настройка: {CODE_DIR / 'install.json'}",
            "",
            "Если нужно удалить всё: удали эти папки вручную и (по желанию)",
            "переменную окружения POWERMILL_DATA_ROOT (Параметры -> Переменные среды).",
        ]
    else:
        lines += ["", "install.json не найден — папку данных определяй сам "
                      "(ищи папку powermill-ai)."]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        print(line)
    print()
    print(f"📝 Отчёт: {REPORT}")
    print("Макросы в PowerMill можно убрать вручную: папка макросов -> файлы "
          "PM_AI_*.mac.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

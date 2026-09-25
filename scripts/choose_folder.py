"""
Сменить папку данных (пункт 42 меню).

Тяжёлое (справка, базы поиска, отчёты) может лежать где угодно: у одного это
диск E:, у другого диск C:, у третьего — внешний диск. Этот пункт спрашивает
папку и запоминает выбор в `install.json`, чтобы его видела и программа, и
проверка компьютера, и установщик.

Что делает:
1. показывает текущую папку данных и откуда она взялась;
2. открывает окно выбора папки (или спрашивает текстом, если окна нет);
3. проверяет, что в папку можно писать, — иначе просит выбрать другую;
4. создаёт подпапки (данные, база поиска, output) и пишет install.json;
5. пишет отчёт `output\\data_root_report.txt` и говорит, что нажать дальше.

Запуск: пункт 42 меню (scripts\\choose_folder.bat) или кнопка «Сменить папку
данных…» в окне приложения (пункт 39).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                            # noqa: E402
from src.applog import start_log                          # noqa: E402

SUBFOLDERS = ("data/pdf", "data/videos", "data/macros", "data/forums",
              "chroma_db", "output")
REPORT_FILE = Path(config.OUTPUT_DIR) / "data_root_report.txt"


def folder_problem(path: Path) -> str:
    """Пусто — писать можно; иначе текст проблемы (чтобы объяснить человеку)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".powerMillAI_probe"
        probe.write_text("проверка", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return f"в папку «{path}» писать нельзя: {error}"
    return ""


def make_subfolders(path: Path) -> None:
    for sub in SUBFOLDERS:
        try:
            (path / sub).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def save_choice(path: Path | str, python: str | None = None) -> list[str]:
    """Проверяет папку, создаёт подпапки и записывает выбор. Возвращает строки."""
    root = Path(path).expanduser()
    lines = [f"Папка данных: {root}"]
    problem = folder_problem(root)
    if problem:
        lines.append("(!) " + problem)
        lines.append("    Папка не изменена — выбери другую.")
        return lines
    make_subfolders(root)
    try:
        settings = config.save_data_root(root)
    except OSError as error:
        lines.append(f"(!) не смог записать настройку: {error}")
        return lines
    lines.append(f"Настройка сохранена: {settings}")
    lines.append("Перезапусти окно приложения — дальше данные лежат здесь.")
    return lines


def best_start_dir() -> str:
    """Откуда открывать окно выбора: текущая папка, иначе домашняя."""
    root = Path(config.DATA_ROOT)
    if root.exists():
        return str(root)
    for parent in (root.parent, Path.home()):
        if parent.exists():
            return str(parent)
    return str(Path.home())


def ask_with_dialog(start: str) -> str:
    """Окно выбора папки. Если tkinter нет — спрашиваем текстом."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:                                     # noqa: BLE001
        print("(окна выбора нет — напиши путь вручную)")
        try:
            return input(f"Папка данных (Enter — оставить {config.DATA_ROOT}): ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""
    root = tk.Tk()
    root.withdraw()
    chosen = filedialog.askdirectory(
        title="Куда складывать данные PowerMill AI (справка, базы, отчёты)",
        initialdir=start, mustexist=False)
    root.destroy()
    return chosen or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сменить папку данных PowerMill AI")
    parser.add_argument("--path", help="папка (без вопроса — для проверок)")
    parser.add_argument("--show", action="store_true", help="только показать текущую")
    args = parser.parse_args(argv)

    log = start_log("choose_folder")
    root, source = config.requested_data_root()
    print("=" * 64)
    print("  ПАПКА ДАННЫХ (пункт 42)")
    print("=" * 64)
    print(f"  Сейчас:  {config.DATA_ROOT}")
    print(f"  Источник: {source}")
    print(f"  Хотелось: {root}")
    notes = list(getattr(config, "DATA_ROOT_NOTE", []))
    for note in notes:
        print("  (!) " + note)
    print(f"  Лог:     {log}")
    print()

    if args.show:
        return 0

    if args.path:
        chosen = args.path
    else:
        print("Выбери папку для данных: справка, базы поиска, отчёты, скачанные видео.")
        print(f"Сейчас используется: {config.DATA_ROOT}")
        print("Совет: отдельный диск (E:, D:) или папка пользователя. Диск C: тоже "
              "годится, если места хватает.")
        print()
        chosen = ask_with_dialog(best_start_dir())
    if not chosen:
        print("Выбор отменён — ничего не менял.")
        print(f"Осталась прежняя папка: {config.DATA_ROOT}")
        return 1

    lines = save_choice(chosen)
    for line in lines:
        print("  " + line)
    print()

    ok = not any(line.startswith("(!)") for line in lines)
    report = [
        "=" * 64,
        "  ПАПКА ДАННЫХ PowerMill AI (пункт 42)",
        "=" * 64,
        f"  Было:     {config.DATA_ROOT}",
        f"  Стало:    {Path(chosen)}",
        f"  Настройка: {lines[-1] if len(lines) > 1 else lines[0]}",
        "",
        *lines,
        "",
        "Дальше:",
        "  1) окно приложения -> кнопка «Перезапустить» (или закрой и открой заново);",
        "  2) в окне будет видна новая папка данных;",
        "  3) если хочешь перенести уже скачанные материалы — скопируй папки",
        "     data, chroma_db и output вручную (программа их не переносит).",
    ]
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")
    except OSError:
        pass
    print(f"📝 Отчёт: {REPORT_FILE}")
    if ok:
        print("Папка изменена. Открой окно заново — дальше данные будут здесь.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

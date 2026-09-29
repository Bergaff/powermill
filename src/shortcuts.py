"""
Ярлыки в меню «Пуск» и на рабочем столе (для установки «под ключ»).

Зачем: у другого человека не должно быть «запусти вот этот батник в папке».
Он должен видеть **программу в меню «Пуск»** и на рабочем столе, как любую
другую. Ярлыки создаём через PowerShell (WScript.Shell) — никаких лишних
библиотек, работает на любой Windows 10/11.

Модуль ничего не делает при импорте: только строит команды и, если попросят,
выполняет их. Поэтому его удобно проверять тестами на любом компьютере.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "PowerMill AI"
APP_BAT = "start_app.bat"
MENU_BAT = "start_menu.bat"
ICON_FILE = Path("assets") / "app.ico"


@dataclass(frozen=True)
class Shortcut:
    """Один ярлык: что, куда, с какими аргументами."""

    name: str
    target: Path
    folder: str                     # "desktop" | "menu"
    arguments: str = ""
    workdir: Path | None = None
    icon: Path | None = None

    @property
    def file_name(self) -> str:
        return f"{self.name}.lnk"


def desktop_folder() -> Path:
    """Рабочий стол пользователя (без Windows-переменных, если их нет)."""
    import os

    profile = os.getenv("USERPROFILE")
    if profile:
        return Path(profile) / "Desktop"
    return Path.home() / "Desktop"


def start_menu_folder(app_name: str = APP_NAME) -> Path:
    """Папка программы в меню «Пуск»."""
    import os

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / app_name
    return Path.home() / "Start Menu" / "Programs" / app_name


def app_shortcuts(project_dir: Path | str = PROJECT_ROOT,
                  app_name: str = APP_NAME) -> list[Shortcut]:
    """Что создать: приложение, меню отчётов, чтение отчётов."""
    root = Path(project_dir)
    icon = root / ICON_FILE
    icon_arg = icon if icon.exists() else None
    return [
        Shortcut(f"{app_name}", root / APP_BAT, "desktop",
                 workdir=root, icon=icon_arg),
        Shortcut(f"{app_name}", root / APP_BAT, "menu",
                 workdir=root, icon=icon_arg),
        Shortcut(f"{app_name} — меню пунктов", root / MENU_BAT, "menu",
                 workdir=root, icon=icon_arg),
        Shortcut(f"{app_name} — отчёты", root / "scripts" / "show_reports.bat", "menu",
                 workdir=root, icon=icon_arg),
        Shortcut(f"{app_name} — проверка компьютера",
                 root / "scripts" / "doctor.bat", "menu",
                 workdir=root, icon=icon_arg),
    ]


def folder_for(shortcut: Shortcut, app_name: str = APP_NAME) -> Path:
    return desktop_folder() if shortcut.folder == "desktop" \
        else start_menu_folder(app_name)


def powershell_command(shortcut: Shortcut, folder: Path) -> list[str]:
    """Команда PowerShell, создающая ярлык (COM WScript.Shell)."""
    link = folder / shortcut.file_name
    parts = [
        "$w = New-Object -ComObject WScript.Shell;",
        f"$s = $w.CreateShortcut('{link}');",
        f"$s.TargetPath = '{shortcut.target}';",
        f"$s.WorkingDirectory = '{shortcut.workdir or shortcut.target.parent}';",
    ]
    if shortcut.arguments:
        parts.append(f"$s.Arguments = '{shortcut.arguments}';")
    if shortcut.icon is not None:
        parts.append(f"$s.IconLocation = '{shortcut.icon}';")
    parts.append("$s.Description = 'PowerMill AI — ассистент технолога';")
    parts.append("$s.Save();")
    script = " ".join(parts)
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


def plan_lines(project_dir: Path | str = PROJECT_ROOT,
               app_name: str = APP_NAME) -> list[str]:
    """Что будет создано — до создания."""
    lines: list[str] = []
    for shortcut in app_shortcuts(project_dir, app_name):
        folder = folder_for(shortcut, app_name)
        lines.append(f"  • {folder / shortcut.file_name} -> {shortcut.target}")
    return lines


def create(shortcut: Shortcut, app_name: str = APP_NAME,
           dry_run: bool = False) -> tuple[bool, str]:
    """Создаёт ярлык. Возвращает (получилось, пояснение)."""
    folder = folder_for(shortcut, app_name)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return False, f"не смог создать папку {folder}: {error}"

    command = powershell_command(shortcut, folder)
    if dry_run:
        return True, " ".join(command)
    if sys.platform != "win32":
        return False, "ярлыки .lnk делает только Windows"
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"PowerShell не сработал: {error}"
    link = folder / shortcut.file_name
    if done.returncode == 0 and link.exists():
        return True, str(link)
    note = (done.stderr or done.stdout or "").strip()
    return False, note or f"ярлык не появился: {link}"


def create_all(project_dir: Path | str = PROJECT_ROOT, app_name: str = APP_NAME,
               dry_run: bool = False) -> list[tuple[Path, bool, str]]:
    """Создаёт все ярлыки. Возвращает [(ярлык, получилось, пояснение)]."""
    result: list[tuple[Path, bool, str]] = []
    for shortcut in app_shortcuts(project_dir, app_name):
        ok, note = create(shortcut, app_name, dry_run=dry_run)
        result.append((folder_for(shortcut, app_name) / shortcut.file_name, ok, note))
    return result


def remove_all(project_dir: Path | str = PROJECT_ROOT,
               app_name: str = APP_NAME) -> list[Path]:
    """Удаляет созданные ярлыки (для удаления программы)."""
    removed: list[Path] = []
    for shortcut in app_shortcuts(project_dir, app_name):
        link = folder_for(shortcut, app_name) / shortcut.file_name
        try:
            if link.exists():
                link.unlink()
                removed.append(link)
        except OSError:
            continue
    folder = start_menu_folder(app_name)
    try:
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass
    return removed

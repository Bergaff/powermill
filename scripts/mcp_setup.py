"""
Подключение PowerMill AI к ИИ-клиенту по MCP (пункт 44 меню).

Что делает
----------
Прописывает наш MCP-сервер в настройки ИИ-клиента, чтобы в чате клиента
появились инструменты PowerMill AI («посчитай режимы», «покажи, что открыто в
PowerMill», «составь макрос»).

Что важно
---------
* **Ничего не перезаписываем молча.** Если файл настроек уже есть, сначала
  делается копия рядом (`*.bak`), а наш сервер добавляется к существующим —
  чужие серверы остаются на месте.
* **Понятный отказ.** Если клиента нет или папка недоступна — печатаем готовый
  кусок JSON, который человек вставит сам (и объясняем, куда).
* **Тот же Python, что у программы.** В настройки пишется путь к venv-окружению
  проекта (там стоит pywin32), поэтому инструменты работают с PowerMill
  напрямую. Если venv нет — берётся текущий Python и об этом говорится.

Запуск: пункт 44 меню (scripts\\mcp_setup.bat) или
        python -m scripts.mcp_setup [--show | --write all | --remove]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                            # noqa: E402
from src.applog import start_log                          # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "powermill-ai"
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "mcp_server.py"
REPORT_FILE = Path(config.OUTPUT_DIR) / "mcp_report.txt"


# --------------------------------------------------------------------------
# Клиенты и их файлы настроек
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Client:
    """Один ИИ-клиент: где лежит его файл настроек и как он устроен."""

    key: str
    title: str
    path: Path
    top_key: str                      # "mcpServers" (Claude, Cursor) | "servers" (VS Code)
    with_type: bool = False           # VS Code требует "type": "stdio"
    note: str = ""


def _appdata() -> Path:
    return Path(os.getenv("APPDATA", str(Path.home())))


def clients() -> list[Client]:
    home = Path.home()
    return [
        Client("claude", "Claude Desktop (приложение)",
               _appdata() / "Claude" / "claude_desktop_config.json", "mcpServers",
               note="после записи закрой и снова открой Claude"),
        Client("cursor", "Cursor",
               home / ".cursor" / "mcp.json", "mcpServers",
               note="в Cursor: Settings -> MCP — там будет видно инструменты"),
        Client("vscode", "VS Code (Copilot / Agent)",
               _appdata() / "Code" / "User" / "mcp.json", "servers",
               with_type=True,
               note="в VS Code: панель Copilot -> Agent -> MCP Servers"),
        Client("windsurf", "Windsurf",
               home / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers"),
        Client("project", "Этот проект (Claude Code и другие клиенты рядом с кодом)",
               PROJECT_ROOT / ".mcp.json", "mcpServers",
               note="файл .mcp.json читают клиенты, запущенные в этой папке"),
    ]


def find_client(key: str) -> Client | None:
    for client in clients():
        if client.key == key:
            return client
    return None


# --------------------------------------------------------------------------
# Что прописываем
# --------------------------------------------------------------------------
def server_python() -> tuple[Path, str]:
    """Python для сервера: сначала venv проекта (в нём pywin32), потом текущий."""
    for candidate in (PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
                      PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
                      PROJECT_ROOT / ".venv" / "bin" / "python",
                      PROJECT_ROOT / "venv" / "bin" / "python"):
        if candidate.exists():
            return candidate, f"окружение проекта ({candidate.parent.parent.name})"
    return Path(sys.executable), "текущий Python (venv не найден)"


def server_entry(client: Client | None = None) -> dict:
    """Готовый блок настроек для клиента."""
    python, _source = server_python()
    entry: dict = {"command": str(python), "args": [str(SERVER_SCRIPT)],
                   "cwd": str(PROJECT_ROOT)}
    if client is not None and client.with_type:
        entry = {"type": "stdio", **entry}
    env: dict[str, str] = {}
    for name, key in (("POWERMILL_DATA_ROOT", "data_root"),
                      ("POWERMILL_AI_SETTINGS", "settings")):
        if os.getenv(name):
            env[name] = os.environ[name]
    try:
        root, source = config.requested_data_root()
        if source.startswith("настройка") or source.startswith("значение"):
            env.setdefault("POWERMILL_DATA_ROOT", str(config.DATA_ROOT))
            env.setdefault("POWERMILL_AI_SETTINGS", str(config.settings_path()))
    except Exception:                                         # noqa: BLE001
        pass
    if env:
        entry["env"] = env
    return entry


def config_block(client: Client) -> dict:
    """Файл настроек целиком — то, что человек может скопировать руками."""
    return {client.top_key: {SERVER_NAME: server_entry(client)}}


def json_text(client: Client | None = None) -> str:
    block = config_block(client) if client else {
        "mcpServers": {SERVER_NAME: server_entry()}}
    return json.dumps(block, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Запись и удаление
# --------------------------------------------------------------------------
def write_config(client: Client, entry: dict | None = None) -> list[str]:
    """Добавляет наш сервер в настройки клиента. Чужие серверы не трогает."""
    lines: list[str] = []
    path = client.path
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError) as error:
            return [f"✘ {client.title}: файл настроек не разобрать ({error}).",
                    f"    Починить вручную: {path}",
                    "    Ниже — готовый блок, вставь его сам."]
        if not isinstance(data, dict):
            return [f"✘ {client.title}: в файле не объект JSON — не трогаю: {path}"]
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.copy2(path, backup)
            lines.append(f"    копия прежних настроек: {backup.name}")
        except OSError as error:
            lines.append(f"    (!) копию сделать не удалось: {error}")
    else:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return [f"✘ {client.title}: папки нет и создать не могу ({error})"]

    servers = data.get(client.top_key)
    if not isinstance(servers, dict):
        servers = {}
    servers[SERVER_NAME] = entry if entry is not None else server_entry(client)
    data[client.top_key] = servers
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    except OSError as error:
        return [f"✘ {client.title}: не смог записать ({error})"]
    lines.insert(0, f"✔ {client.title}: прописал в {path}")
    if client.note:
        lines.append("    " + client.note)
    return lines


def remove_config(client: Client) -> list[str]:
    """Убирает наш сервер из настроек (остальное не трогает)."""
    path = client.path
    if not path.exists():
        return [f"• {client.title}: настроек нет — и убирать нечего"]
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError) as error:
        return [f"✘ {client.title}: файл не разобрать ({error}) — не трогаю"]
    servers = data.get(client.top_key)
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        return [f"• {client.title}: нашего сервера там нет"]
    servers.pop(SERVER_NAME)
    if not servers:
        data.pop(client.top_key, None)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    except OSError as error:
        return [f"✘ {client.title}: не смог записать ({error})"]
    return [f"✔ {client.title}: убрал из {path}"]


def configured_clients() -> list[Client]:
    """Где наш сервер уже прописан."""
    found: list[Client] = []
    for client in clients():
        try:
            data = json.loads(client.path.read_text(encoding="utf-8") or "{}")
            if SERVER_NAME in (data.get(client.top_key) or {}):
                found.append(client)
        except (OSError, ValueError):
            continue
    return found


# --------------------------------------------------------------------------
# Отчёт
# --------------------------------------------------------------------------
def report_lines(done: list[str]) -> list[str]:
    import time

    python, source = server_python()
    lines = [
        "=" * 64,
        "  ПОДКЛЮЧЕНИЕ К ИИ-КЛИЕНТУ ПО MCP (пункт 44)",
        "=" * 64,
        f"  Проверено: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Сервер:    {SERVER_SCRIPT}",
        f"  Python:    {python} — {source}",
        f"  Данные:    {config.DATA_ROOT}",
        "",
        "Что сделано:",
    ]
    lines.extend("  " + line for line in done)
    lines += ["", "Где наш сервер уже прописан:"]
    found = configured_clients()
    if found:
        lines.extend(f"  • {client.title}: {client.path}" for client in found)
    else:
        lines.append("  • пока нигде")

    lines += ["", "Как проверить в клиенте:"]
    lines += [
        "  1) закрой и снова открой ИИ-клиент (он читает настройки при запуске);",
        "  2) спроси: «посчитай режимы для Стали 40Х фрезой D16 черновая»;",
        "  3) клиент покажет, что вызвал инструмент powermill_cutting — значит,",
        "     подключение работает.",
        "",
        "Если клиента нет в списке: скопируй блок JSON ниже и вставь в его",
        "настройки MCP сам (формат у всех один — mcpServers).",
        "",
        "Готовый блок:",
        json_text(),
    ]
    return lines


def save_report(done: list[str]) -> Path:
    text = "\n".join(report_lines(done)) + "\n"
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return REPORT_FILE


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------
def ask_yes(question: str, default_yes: bool = True) -> bool:
    hint = "Д/н" if default_yes else "д/Н"
    while True:
        try:
            answer = input(f"{question} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default_yes
        if not answer:
            return default_yes
        if answer in ("д", "да", "y", "yes"):
            return True
        if answer in ("н", "нет", "n", "no"):
            return False
        print("  Ответь «д» или «н».")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Подключить PowerMill AI к ИИ-клиенту (MCP)")
    parser.add_argument("--show", action="store_true",
                        help="только показать блок настроек")
    parser.add_argument("--write", metavar="КЛИЕНТ",
                        help="прописать: all | " + " | ".join(c.key for c in clients()))
    parser.add_argument("--remove", action="store_true",
                        help="убрать наш сервер из настроек")
    parser.add_argument("--yes", action="store_true", help="без вопросов")
    args = parser.parse_args(argv)

    log = start_log("mcp_setup")
    python, source = server_python()
    print("=" * 64)
    print("  ПОДКЛЮЧЕНИЕ К ИИ-КЛИЕНТУ ПО MCP (пункт 44)")
    print("=" * 64)
    print(f"  Сервер: {SERVER_SCRIPT}")
    print(f"  Python: {python} — {source}")
    print(f"  Лог:    {log}")
    print()

    if args.show:
        print("Готовый блок настроек (вставь в настройки MCP своего клиента):")
        print()
        print(json_text())
        saved = save_report(["показан блок настроек"])
        print()
        print(f"📝 Отчёт: {saved}")
        return 0

    if args.remove:
        done: list[str] = []
        for client in configured_clients():
            done.extend(remove_config(client))
        if not done:
            done = ["нашего сервера нигде не было"]
        print("\n".join("  " + line for line in done))
        print()
        print(f"📝 Отчёт: {save_report(done)}")
        return 0

    if args.write:
        keys = ([client.key for client in clients()] if args.write == "all"
                else [args.write.strip()])
        done = []
        for key in keys:
            client = find_client(key)
            if client is None:
                print(f"✘ нет клиента «{key}». Есть: "
                      + ", ".join(c.key for c in clients()))
                return 2
            done.extend(write_config(client))
        for line in done:
            print("  " + line)
        print()
        print(f"📝 Отчёт: {save_report(done)}")
        return 0

    # --- без ключей: показываем и спрашиваем ---
    print("Зачем: у ИИ-клиента (Claude Desktop, Cursor, VS Code) появятся наши")
    print("инструменты — режимы резания, разбор ошибок, план операции, состояние")
    print("PowerMill. Клиент вызывает их сам, тебе достаточно писать в чат.")
    print()
    print("Найденные клиенты:")
    existing = [client for client in clients() if client.path.exists()]
    for client in clients():
        mark = "•" if client.path.exists() else "—"
        print(f"  {mark} {client.title}")
        print(f"      {client.path}")
    print()

    done = []
    if existing:
        for client in existing:
            if args.yes or ask_yes(f"  Прописать в «{client.title}»?", True):
                done.extend(write_config(client))
    if not done:
        project = find_client("project")
        assert project is not None
        print("Готовый блок (вставь в настройки MCP своего клиента):")
        print()
        print(json_text())
        print()
        if args.yes or ask_yes("  Записать его в файл .mcp.json рядом с кодом? "
                               "(его читают клиенты, запущенные в этой папке)", True):
            done.extend(write_config(project))

    print()
    for line in done:
        print("  " + line)
    if not done:
        print("  Ничего не менял — блок настроек выше можно вставить вручную.")
    print()
    saved = save_report(done or ["ничего не менял"])
    print(f"📝 Отчёт: {saved}")
    print("   Перезапусти ИИ-клиент — и спроси: «посчитай режимы для Стали 40Х")
    print("   фрезой D16, черновая». Если клиент вызвал powermill_cutting — работает.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

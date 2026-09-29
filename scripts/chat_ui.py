"""
ИНТЕРФЕЙС АССИСТЕНТА В БРАУЗЕРЕ (пункт 32 меню).

Зачем: в консольном меню не видно, что ассистент делает прямо сейчас, и историю
не полистать. Здесь то же ядро, но в окне браузера: чат, прогресс (строка за
строкой), отчёты рядом, состояние проекта PowerMill и итоги последних макросов.

Запуск: scripts\\chat_ui.bat (или пункт 32 меню). Окно с сервером не закрывать.

Доступ: по умолчанию слушаем только 127.0.0.1 (этот компьютер). Открывать в
локальную сеть (`--host 0.0.0.0`) без нужды не стоит: у интерфейса нет пароля.
"""
from __future__ import annotations

import argparse
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import webui                                    # noqa: E402
from src.applog import start_log                         # noqa: E402


def check(host: str = "127.0.0.1", port: int = 0) -> int:
    """Самопроверка: сервер поднимается и отдаёт страницу."""
    server = webui.make_server(host, port)
    real_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://{host}:{real_port}/", timeout=10) as answer:
            page = answer.read().decode("utf-8", "replace")
        print(f"✔ Интерфейс отвечает (код 200), страница {len(page)} символов")
        print(f"  режимы: {', '.join(webui.MODE_TITLES.values())}")
        return 0
    except Exception as exc:                              # noqa: BLE001
        print(f"❌ Интерфейс не отвечает: {exc}")
        return 1
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PowerMill AI: интерфейс ассистента в браузере (чат + прогресс)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="адрес прослушивания (по умолчанию только свой компьютер)")
    parser.add_argument("--port", type=int, default=8765, help="порт (по умолчанию 8765)")
    parser.add_argument("--open", dest="open_browser", action="store_true", default=True,
                        help="открыть браузер (по умолчанию да)")
    parser.add_argument("--no-open", dest="open_browser", action="store_false",
                        help="не открывать браузер")
    parser.add_argument("--check", action="store_true",
                        help="только проверить, что интерфейс поднимается")
    args = parser.parse_args(argv)

    log = start_log("chat_ui")
    print(f"Лог этого запуска: {log}")
    print()

    if args.check:
        return check()

    return webui.serve(host=args.host, port=args.port,
                       open_browser=args.open_browser)


if __name__ == "__main__":
    sys.exit(main())

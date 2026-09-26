"""
Запуск MCP-сервера PowerMill AI (обычно его запускает сам ИИ-клиент).

Этот файл — «вход», который прописывается в настройках клиента (Claude Desktop,
Cursor, VS Code). Он специально сделан так, чтобы работать **из любой папки**:
клиент запускает Python со своим рабочим каталогом, поэтому путь к проекту
добавляется в sys.path здесь.

Команды человеку::

    python scripts\\mcp_server.py --selftest   # проверить себя (пункт 45 меню)
    python scripts\\mcp_server.py --tools      # список инструментов
    python scripts\\mcp_server.py              # сервер на stdio (для клиента)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.mcp_server import main                           # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

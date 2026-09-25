"""
Логирование для батников: весь вывод скрипта дублируется в файл.

Зачем: при двойном клике по .bat окно может закрыться раньше, чем человек
успеет прочитать ошибку. Тогда батник показывает хвост лога, а лог остаётся
на диске в output\\logs\\ и его можно прислать в чат.

Использование::

    from src.applog import start_log
    log_path = start_log("parse_help")   # весь print() попадёт и в файл
    ...
    print("...")                          # видно и в консоли, и в логе
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR

LOG_DIR = OUTPUT_DIR / "logs"


class _Tee:
    """Пишет одновременно в консоль и в файл (не падает, если что-то из них недоступно)."""

    def __init__(self, stream, file_handle):
        self.stream = stream
        self.file = file_handle

    def write(self, data: str):
        for target in (self.stream, self.file):
            try:
                target.write(data)
            except Exception:  # noqa: BLE001
                pass
        # Сбрасываем сразу, а не при закрытии: если окно закрыли крестиком или
        # сценарий прервали, в логе уже всё есть (иначе последние строки
        # терялись — ровно то, за что человек не успевал прочитать ошибку).
        self.flush()
        return len(data)

    def flush(self):
        for target in (self.stream, self.file):
            try:
                target.flush()
            except Exception:  # noqa: BLE001
                pass

    # некоторые библиотеки проверяют эти атрибуты
    def isatty(self) -> bool:
        return False

    def fileno(self):
        return self.stream.fileno()


_open_log = None  # держим файл открытым на время работы процесса


def start_log(name: str, echo: bool = True) -> Path:
    """Начинает писать stdout/stderr в output\\logs\\<name>.log. Возвращает путь."""
    global _open_log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{name}.log"

    try:
        _open_log = open(path, "w", encoding="utf-8", errors="replace")
    except OSError:
        return path

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _open_log.write(f"# {name}.log — запуск {stamp}\n")
    _open_log.flush()

    if echo:
        sys.stdout = _Tee(sys.__stdout__, _open_log)
        sys.stderr = _Tee(sys.__stderr__, _open_log)
    return path


def log_tail(name: str, lines: int = 60) -> str:
    """Последние строки лога (для показа в батнике после сбоя)."""
    path = LOG_DIR / f"{name}.log"
    if not path.exists():
        return f"(лог {path} не найден)"
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"(не удалось прочитать лог: {e})"
    tail = content[-lines:]
    return "\n".join(tail) if tail else "(лог пуст)"


def log_error_to_file() -> None:
    """Записывает traceback текущего исключения в лог (вызывать в except)."""
    text = traceback.format_exc()
    print(text)
    try:
        if _open_log is not None:
            _open_log.flush()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":  # проверка лога: python -m src.applog
    import sys as _sys

    name = _sys.argv[1] if len(_sys.argv) > 1 else "selfcheck"
    p = start_log(name)
    print("Проверка: эта строка должна попасть и в консоль, и в файл")
    print(f"Путь лога: {p}")
    print(f"Хвост лога:\n{log_tail(name, 5)}")

"""
Файлы, которыми обмениваются макрос PowerMill и ассистент.

Два правила, добытых на живом PowerMill 2026 (24.09.2026):

1. **Кодировка макросов — CP1251, а не UTF-8.**
   PowerMill читает `.mac` как однобайтовый текст в системной кодировке. Наш
   UTF-8-макрос в окне сообщений выглядел как «РџРѕРІРµСЂРєР° РјРѕСЃС‚Р°» —
   то есть PowerMill показывал байты UTF-8 как CP1251. Русские подписи в
   `INPUT`, `MESSAGE` и комментарии из-за этого были нечитаемы. Батники у нас
   остаются в UTF-8 (у них `chcp 65001`), а макросы пишем в CP1251.
   ASCII-часть (команды и пути) от этого не меняется.

2. **Файлы, записанные макросом, читаем «автоопределением».**
   Новые макросы пишут CP1251, но на диске могли остаться файлы от прошлых
   версий (их писал Python в UTF-8) — поэтому сначала пробуем UTF-8, при
   ошибке берём CP1251.

Сюда же — `sanitize()`: в CP1251 нет эмодзи (📚, ⚙️) и стрелки «→», поэтому
перед записью ответа для PowerMill такие символы заменяются на понятные
ASCII-эквиваленты, а не превращаются в мусор.
"""
from __future__ import annotations

from pathlib import Path

# Системная (ANSI) кодировка русской Windows — её понимает PowerMill
PML_ENCODING = "cp1251"

# Символы, которые в CP1251 не влезают, но имеют очевидную замену
REPLACEMENTS = {
    "→": "->",
    "←": "<-",
    "✔": "+",
    "✘": "-",
    "•": "*",
    "⚠": "!",
    "≤": "<=",
    "≥": ">=",
    "×": "x",
    "≈": "~",
}


def sanitize(text: str) -> str:
    """Готовит текст для PowerMill: понятные замены, лишние символы убираем.

    В CP1251 нет эмодзи — если их оставить, `encode(..., errors="replace")`
    превратит каждый в знак вопроса. Поэтому «→» меняем на «->», а эмодзи
    просто выкидываем: текст остаётся читаемым.
    """
    out: list[str] = []
    for char in text or "":
        if char in REPLACEMENTS:
            out.append(REPLACEMENTS[char])
            continue
        try:
            char.encode(PML_ENCODING)
        except UnicodeEncodeError:
            continue                      # эмодзи и другие неподдерживаемые
        out.append(char)
    return "".join(out)


def encode(text: str) -> bytes:
    """Текст макроса/ответа → байты в кодировке PowerMill (CP1251)."""
    return sanitize(text).encode(PML_ENCODING, errors="replace")


def write(path: Path | str, text: str, crlf: bool = True) -> Path:
    """Записывает файл для PowerMill: CP1251 и (по умолчанию) переводы строк CRLF."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = text.replace("\r\n", "\n")
    if crlf:
        body = body.replace("\n", "\r\n")
    target.write_bytes(encode(body))
    return target


def decode(data: bytes) -> str:
    """Байты файла от PowerMill → текст (UTF-8, иначе CP1251)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(PML_ENCODING, errors="replace")


def read(path: Path | str) -> str:
    """Читает файл, который мог записать макрос PowerMill (любая из кодировок)."""
    target = Path(path)
    return decode(target.read_bytes())


# --------------------------------------------------------------------------
# Имена файловых дескрипторов в макросах
# --------------------------------------------------------------------------
# PowerMill держит открытый макросом файл до `FILE CLOSE` — и на всю СЕССИЮ.
# Если макрос оборвался на ошибке (а на живой машине так и было: выражение
# `$Block.XLength` остановило макрос на 31-й строке), `FILE CLOSE` не выполнился,
# и следующая попытка открыть файл тем же именем падает: «handle уже
# используется out». Поэтому имя дескриптора делаем УНИКАЛЬНЫМ: своё на каждую
# часть и на каждый запуск. Тогда оборванный макрос ничего не ломает.
_handle_counter = 0


def file_handle(prefix: str = "o") -> str:
    """Уникальное имя файлового дескриптора для макроса (буквы и цифры)."""
    global _handle_counter
    import time

    _handle_counter += 1
    token = (time.strftime("%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
             + f"{_handle_counter:02d}")
    return f"{prefix}{token}"


def legacy_handles() -> tuple[str, ...]:
    """Имена, которыми пользовались прежние версии (могут «залипнуть»)."""
    return ("out", "chkout", "askq", "aska", "tfile", "marka", "tread",
            "chk", "pmout")


def release_handles(session, names: tuple[str, ...] | None = None) -> list[str]:
    """Пробует освободить «залипшие» имена файлов после оборванного макроса.

    Результат не проверяем: если имя не занято, PowerMill просто ответит
    ошибкой команды — это нормально и никому не мешает. `session` — любой
    объект с методом `execute(команда)` (у нас это `src.pm_com.LiveSession`).
    """
    released: list[str] = []
    for name in (names if names is not None else legacy_handles()):
        try:
            session.execute(f"FILE CLOSE {name}")
            released.append(name)
        except Exception:  # noqa: BLE001
            continue
    return released


def unique_handles(text: str, names: tuple[str, ...] | None = None) -> str:
    """Делает имена файловых дескрипторов в тексте макроса уникальными.

    PowerMill держит открытый макросом файл до `FILE CLOSE` — и на всю сессию.
    Оборванный на ошибке макрос до `FILE CLOSE` не доходит, и следующий запуск
    падает с «handle уже используется <имя>» (это и случилось на живой машине:
    макрос встал на строке с размерами заготовки, а файл остался открытым).
    Проще не бороться с этим, а не переиспользовать имя: к каждому добавляется
    уникальный числовой хвост — свой на каждый запуск.

    Меняются ТОЛЬКО места, где имя стоит после `AS` / `TO` / `CLOSE` / `FROM`
    (это и есть дескрипторы). Текст в кавычках и пути не трогаем: папка с
    именем `out` или строка «out of range» должны остаться как были.
    """
    import re

    # Список — все имена, которыми пользуются наши макросы (см. grep "AS <имя>"
    # по src): собираем его явно, чтобы имя не «залипло» после сбоя.
    patterns = names or ("out", "chkout", "ncout", "nc_after", "askq", "aska",
                         "chk_a", "chk_b", "chk_c", "chk2", "chk", "tfile",
                         "tfinal", "tread", "marka", "markb", "markc", "markd",
                         "marke", "pmout", "output", "inp", "snip", "rank")
    token = file_handle("")[1:]                     # только цифровой хвост
    for pattern in sorted(patterns, key=len, reverse=True):
        name = rf"{re.escape(pattern)}\d*"
        for keyword in ("AS", "TO", "CLOSE", "FROM"):
            text = re.sub(rf"(?<=\b{keyword} ){name}\b",
                          lambda match: match.group(0) + token, text)
    return text

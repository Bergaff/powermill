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

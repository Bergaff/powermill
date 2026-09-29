"""
Извлечение ЧИТАЕМОГО текста из оффлайн-справки PowerMill.

Почему это отдельный модуль
---------------------------
Справка Autodesk PowerMill (2024-2026) собрана генератором «wrapped HTML»:

    Help\\l.rus\\
        files\\GUID-XXXX.htm          <- ~850 байт: только служебные скрипты,
                                        браузер достраивает страницу в JS.
        wrapped-files\\GUID-XXXX.htm.js <- 0.5-55 КБ: НАСТОЯЩИЙ текст страницы
                                        (HTML, зашитый внутрь JS-строки).
        scripts\\toc-treedata.js      <- дерево оглавления со всеми заголовками.
        scripts\\search-entries1.js   <- предрассчитанный поисковый индекс.

Поэтому наивный BeautifulSoup по `files\\*.htm` даёт пустоту (0.8 КБ скриптов),
и вся документация «пропадает». Что делает модуль:

1. `decode_html`      — угадывает кодировку (RU-справка бывает cp1251).
2. `js_string_literals` — вытаскивает строковые литералы из JS с корректной
   раскодировкой escape-последовательностей (\\n, \\", \\u0410, \\xNN).
3. `unwrap_wrapped_js` — собирает из литералов настоящий HTML страницы
   (в том числе склеенные конкатенацией `"a" + "b"`).
4. `html_to_structured_text` — превращает HTML в структурированный текст:
   заголовки `##`, списки `- `, таблицы `| a | b |`, код с отступом,
   ссылки на картинки `[рисунок: ...]`.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

try:  # bs4 есть в requirements.txt; без него работает regex-фолбэк
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


# --------------------------------------------------------------------------
# 1. Кодировки
# --------------------------------------------------------------------------
def decode_html(raw: bytes) -> str:
    """Байты -> текст: meta charset -> BOM -> utf-8 -> cp1251 (рус. справка)."""
    if not raw:
        return ""
    m = re.search(br"charset\s*=\s*[\"']?([\w\-]+)", raw[:4096], re.I)
    if m:
        cs = m.group(1).decode("ascii", "ignore").lower()
        try:
            return raw.decode(cs, errors="replace")
        except LookupError:
            pass
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    for enc in ("utf-8", "cp1251", "windows-1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1251", errors="replace")  # cp1251 не бросает ошибок


def _fix_surrogates(text: str) -> str:
    """\\ud83d\\ude00 -> один символ (иначе UnicodeEncodeError при записи)."""
    if not any("\ud800" <= ch <= "\udfff" for ch in text):
        return text
    try:
        return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    except Exception:
        return text.encode("utf-8", "replace").decode("utf-8")


# --------------------------------------------------------------------------
# 2. JS: строковые литералы и их раскодировка
# --------------------------------------------------------------------------
_JS_SIMPLE_ESCAPES = {
    "n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v",
    "0": "\0", "/": "/", "\\": "\\", '"': '"', "'": "'", "`": "`",
}


def unescape_js(text: str) -> str:
    """Раскодирует escape-последовательности JS-строки."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        e = text[i + 1]
        if e == "u" and i + 6 <= n and re.fullmatch(r"[0-9a-fA-F]{4}", text[i + 2:i + 6]):
            out.append(chr(int(text[i + 2:i + 6], 16)))
            i += 6
            continue
        if e == "x" and i + 4 <= n and re.fullmatch(r"[0-9a-fA-F]{2}", text[i + 2:i + 4]):
            out.append(chr(int(text[i + 2:i + 4], 16)))
            i += 4
            continue
        if e == "\n":          # перенос строки через backslash
            i += 2
            continue
        if e in _JS_SIMPLE_ESCAPES:
            out.append(_JS_SIMPLE_ESCAPES[e])
            i += 2
            continue
        out.append(e)
        i += 2
    return _fix_surrogates("".join(out))


def js_string_literals(src: str) -> list[tuple[int, int, str]]:
    """Все строковые литералы файла: [(start, end, значение), ...].

    Комментарии пропускаются, «оборванные» строки игнорируются.
    """
    out: list[tuple[int, int, str]] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            quote = c
            j = i + 1
            raw_chars: list[str] = []
            terminated = False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    raw_chars.append(src[j:j + 2])
                    j += 2
                    continue
                if ch == quote:
                    terminated = True
                    break
                if ch == "\n":       # незакрытая строка — не литерал
                    break
                raw_chars.append(ch)
                j += 1
            if terminated:
                out.append((i, j + 1, unescape_js("".join(raw_chars))))
                i = j + 1
                continue
            i = j + 1 if j > i else i + 1
            continue
        if c == "`":
            j = src.find("`", i + 1)
            if j == -1:
                break
            out.append((i, j + 1, _fix_surrogates(src[i + 1:j])))
            i = j + 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        i += 1
    return out


_TAG_RE = re.compile(
    r"<\s*(?:/)?\s*(?:p|div|span|br|h[1-6]|ul|ol|li|table|tr|td|th|b|i|u|a|img|"
    r"font|strong|em|blockquote|pre|code|tbody|thead|center|sup|sub|"
    r"html|head|body|title|meta|script|style|link|dl|dt|dd|hr|section|article)\b",
    re.I,
)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\s+html", re.I)


def _looks_like_html(text: str) -> bool:
    """HTML ли это. Важно: страницы-редиректы справки содержат только
    html/head/meta/title/body — без div/p, поэтому проверяем и DOCTYPE."""
    head = text[:3000]
    if _DOCTYPE_RE.search(head) or "<html" in head.lower():
        return True
    return bool(_TAG_RE.search(head))


def _group_literals(src: str, literals: list[tuple[int, int, str]]) -> list[str]:
    """Склеивает литералы, соединённые '+': "a" +\\n "b" -> ["ab"]."""
    groups: list[str] = []
    current: list[str] = []
    prev_end: int | None = None
    for start, end, value in literals:
        if prev_end is None:
            current = [value]
        else:
            between = src[prev_end:start]
            # между литералами допустимы только + , пробелы и переносы
            if re.fullmatch(r"[\s+,]*", between):
                current.append(value)
            else:
                if current:
                    groups.append("".join(current))
                current = [value]
        prev_end = end
    if current:
        groups.append("".join(current))
    return groups


# Если HTML пришёл несколькими кусками (document.write/append), то это одна
# страница — склеиваем. Ниже этого суммарного размера считаем куски мусором.
_JOIN_MIN_TOTAL = 80


def unwrap_wrapped_js(js: str, min_html_len: int = 200) -> str:
    """JS-файл обёртки -> HTML страницы (или длинный текст как есть).

    Возвращает "" если внутри нет ничего похожего на содержимое страницы.
    """
    if not js.strip():
        return ""

    # (а) в файле уже лежит готовый HTML (некоторые сборки справки так делают)
    stripped = js.lstrip()
    if stripped[:1] == "<" and _looks_like_html(js[:2000]):
        return js

    literal_groups = _group_literals(js, js_string_literals(js))
    html_groups = [g for g in literal_groups if _looks_like_html(g)]

    # (б) HTML, разбитый на несколько document.write(...) / .append(...)
    if html_groups:
        total = sum(len(g) for g in html_groups)
        # Несколько кусков — это одна страница, склеиваем по порядку.
        # Порог защищает от случая «много мелких UI-шаблонов + один текст».
        if len(html_groups) > 1 and total >= min(min_html_len, _JOIN_MIN_TOTAL):
            return "\n".join(html_groups)
        return max(html_groups, key=len)

    # (в) HTML нет, но есть длинный текст (иногда обёртка хранит plain text)
    if literal_groups:
        longest = max(literal_groups, key=len)
        if len(longest) >= min_html_len:
            return longest

    # (г) последний шанс: выкинуть JS-код, оставить «человекочитаемое»
    guess = re.sub(r"(?is)<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", " ", js)
    guess = re.sub(r"[{};]", "\n", guess)
    guess = re.sub(r"\b(?:function|var|let|const|return|document|window)\b[^\n]*", " ", guess)
    guess = unescape(guess)
    guess = re.sub(r"[ \t]+", " ", guess)
    return guess if len(guess.strip()) >= min_html_len else ""


# --------------------------------------------------------------------------
# 3. HTML -> структурированный текст
# --------------------------------------------------------------------------
_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Служебные блоки справки: панель навигации, «было полезно?», копирайты и т.п.
_JUNK_SELECTORS = (
    "script", "style", "noscript", "nav", "header", "footer", "iframe", "form",
    "#breadcrumbs", ".breadcrumbs", ".breadcrumb", ".MCBreadcrumbsBox",
    ".navigation", ".nav", ".navbar", ".footer", ".header", ".topicToolbar",
    ".MCWebHelpFramesetLink", ".MCWebHelpSearchResults", "#show-hide-navigation",
    ".search-filter", ".toolbar", ".menu", ".MCTopicToolbar", ".me_nav",
)
_JUNK_CLASS_RE = re.compile(
    r"(breadcrumb|toolbar|copyright|footer|nav(igation)?|search-?box)", re.I
)


def _node_text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def html_to_structured_text(html: str, keep_images: bool = True) -> str:
    """HTML -> текст с сохранением структуры (заголовки, списки, таблицы, код)."""
    if not html or not html.strip():
        return ""

    if BeautifulSoup is None:  # regex-фолбэк (без зависимостей)
        return _regex_html_to_text(html, keep_images=keep_images)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_JUNK_SELECTORS):
        tag.decompose()
    for tag in soup.find_all(True):
        if not tag.attrs:
            continue
        cls = " ".join(tag.get("class") or [])
        tid = tag.get("id") or ""
        if cls and _JUNK_CLASS_RE.search(cls):
            tag.decompose()
        elif tid and _JUNK_CLASS_RE.search(tid):
            tag.decompose()

    root = soup.body or soup
    lines: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        line = re.sub(r"[ \t\u00a0]+", " ", "".join(buf)).strip()
        buf.clear()
        if line:
            lines.append(line)

    def add(text: str) -> None:
        if text:
            buf.append(text)

    def render_table(table) -> None:
        flush()
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"])
            row = [_node_text(c) for c in cells]
            if any(row):
                rows.append(row)
        if not rows:
            return
        width = max(len(r) for r in rows)
        for idx, row in enumerate(rows):
            row += [""] * (width - len(row))
            lines.append("| " + " | ".join(cell or " " for cell in row) + " |")
            if idx == 0:
                lines.append("|" + "|".join([" --- "] * width) + "|")
        lines.append("")

    def render(node, list_prefix: str = "") -> None:
        name = getattr(node, "name", None)
        if name is None:  # NavigableString
            text = str(node)
            if text.strip():
                add(re.sub(r"\s+", " ", text))
            return

        if name in _HEADING_LEVELS:
            flush()
            title = _node_text(node)
            if title:
                lines.append("")
                lines.append("#" * _HEADING_LEVELS[name] + " " + title)
                lines.append("")
            return
        if name == "table":
            render_table(node)
            return
        if name in ("ul", "ol"):
            flush()
            for i, li in enumerate(node.find_all("li", recursive=False), 1):
                flush()
                marker = "- " if name == "ul" else f"{i}. "
                buf.append(marker)
                render(li)
                flush()
            lines.append("")
            return
        if name == "li":
            for child in node.children:
                render(child, list_prefix)
            return
        if name in ("pre", "code") and name == "pre":
            flush()
            code = node.get_text("\n").rstrip()
            if code.strip():
                lines.append("```")
                lines.extend(code.splitlines())
                lines.append("```")
                lines.append("")
            return
        if name == "img":
            if keep_images:
                alt = (node.get("alt") or node.get("title") or "").strip()
                src = (node.get("src") or "").strip()
                label = alt or Path(src).stem or "изображение"
                add(f" [рисунок: {label}] ")
            return
        if name == "br":
            flush()
            return
        if name in ("p", "div", "section", "article", "blockquote", "dl", "dt", "dd",
                    "tr", "td", "th", "figcaption", "caption", "body", "html", "center",
                    "tbody", "thead", "table"):
            if name in ("dt",):
                add(_node_text(node) + " — ")
                return
            for child in node.children:
                render(child, list_prefix)
            flush()
            return
        for child in node.children:
            render(child, list_prefix)

    render(root)
    flush()

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _regex_html_to_text(html: str, keep_images: bool = True) -> str:
    """Фолбэк без bs4: грубое, но рабочее преобразование HTML в текст."""
    # head целиком (title/meta/ссылки на скрипты) — это НЕ содержимое страницы,
    # иначе заголовок попадал бы в тело (важно для страниц-редиректов)
    text = re.sub(r"(?is)<head\b[^>]*>.*?</head\s*>", " ", html)
    text = re.sub(r"(?is)<title\b[^>]*>.*?</title\s*>", " ", text)
    text = re.sub(r"(?is)<meta\b[^>]*>", " ", text)
    text = re.sub(r"(?is)<link\b[^>]*>", " ", text)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<\s*(script|style|noscript)\b[^>]*>.*?<\s*/\s*\1\s*>", " ", text)
    if not keep_images:
        text = re.sub(r"(?is)<img[^>]*>", " ", text)
    else:
        text = re.sub(
            r"(?is)<img[^>]*?(?:alt|title)\s*=\s*[\"']([^\"']*)[\"'][^>]*>",
            r" [рисунок: \1] ",
            text,
        )
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*/\s*(p|div|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"(?is)<(h[1-6])[^>]*>", r"\n\n## ", text)
    text = re.sub(r"(?is)<\s*li[^>]*>", "\n- ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


# --------------------------------------------------------------------------
# 4. Файл -> (заголовок, текст)
# --------------------------------------------------------------------------
_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_H1_RE = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")


def guess_title(html_or_text: str, fallback: str = "") -> str:
    """Заголовок страницы: <h1> -> <title> -> первая строка -> имя файла."""
    if html_or_text:
        m = _H1_RE.search(html_or_text[:20000])
        if m:
            title = _node_text_simple(m.group(1))
            if title:
                return title
        m = _TITLE_RE.search(html_or_text[:20000])
        if m:
            title = _node_text_simple(m.group(1))
            if title:
                # «PowerMill: Новые возможности» -> «Новые возможности»
                return re.sub(r"^[^:]{0,30}:\s*", "", title).strip() or title
        heading = re.search(r"(?m)^#{1,3}\s+(.+)$", html_or_text)
        if heading:
            return heading.group(1).strip()
    return fallback


def _node_text_simple(fragment: str) -> str:
    text = re.sub(r"(?s)<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def extract_page_text(raw: bytes, path: Path | None = None) -> tuple[str, str]:
    """Байты страницы справки -> (заголовок, структурированный текст).

    Понимает оба вида файлов справки: обычный HTML и wrapped-обёртку в JS.
    """
    data = decode_html(raw)
    fallback_title = path.stem if path else ""
    is_js = path is not None and path.suffix.lower() == ".js"

    html = data
    if is_js or not _looks_like_html(data):
        unwrapped = unwrap_wrapped_js(data)
        if unwrapped and _looks_like_html(unwrapped):
            html = unwrapped
        elif unwrapped and len(unwrapped.strip()) > len(html.strip()):
            html = unwrapped

    title = guess_title(html, fallback=fallback_title)
    text = html_to_structured_text(html) if _looks_like_html(html) else _plain_text(html)
    if not text.strip() and _looks_like_html(data):
        text = html_to_structured_text(data)
    return title, text


def _plain_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip()).strip()


# --------------------------------------------------------------------------
# 5. Метаданные страниц справки (Autodesk: topicid, contextid, topic-type)
# --------------------------------------------------------------------------
_META_RE = re.compile(r'<meta\s+name="([\w\-]+)"\s+content="([^"]*)"', re.I)
_GUID_RE = re.compile(r"GUID-[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}", re.I)


def extract_meta(html: str) -> dict:
    """<meta name=... content=...> -> словарь (topicid, contextid, topic-type, ...)."""
    meta: dict[str, str] = {}
    for name, content in _META_RE.findall(html):
        key = name.strip().lower()
        if key not in meta:
            meta[key] = content.strip()
    if "topicid" not in meta:
        guid = _GUID_RE.search(html[:4000])
        if guid:
            meta["topicid"] = guid.group(0)
    return meta


_GUID_HREF_RE = re.compile(
    r"""["'](?:\.\./)?(?:\./)?(files/)?(GUID-[0-9A-Fa-f\-]{4,40}\.htm)["']""",
    re.I,
)


def find_redirect_target(html: str) -> str:
    """Куда ведёт страница-редирект: 'files/GUID-....htm' (или '').

    Типичный вид в справке Autodesk:
        window.location.href = "../files/GUID-0001-....htm";
    """
    m = _GUID_HREF_RE.search(html)
    if m:
        name = m.group(2)
        # нормализуем к виду files/GUID-....htm (так же, как в оглавлении)
        return name if name.lower().startswith("files/") else f"files/{name}"
    guid = _GUID_RE.search(html)
    if guid:
        return f"files/{guid.group(0)}.htm"
    return ""


def load_page(path: Path) -> dict:
    """Файл справки -> {title, text, html, meta, topic_type, redirect_to}."""
    try:
        raw = path.read_bytes()
    except OSError:
        return {"title": "", "text": "", "html": "", "meta": {}, "topic_type": "",
                "redirect_to": ""}

    data = decode_html(raw)
    is_js = path.suffix.lower() == ".js"
    html = data
    if is_js or not _looks_like_html(data):
        unwrapped = unwrap_wrapped_js(data)
        if unwrapped:
            html = unwrapped

    meta = extract_meta(data)
    if html is not data:
        # в .htm-заглушке метаданные есть всегда; в wrapped-файле они тоже могут
        # быть — добираем то, чего не хватает
        for key, value in extract_meta(html).items():
            meta.setdefault(key, value)

    title = guess_title(html, fallback=path.stem)
    text = html_to_structured_text(html) if _looks_like_html(html) else _plain_text(html)

    # Страница-редирект: полезного текста в ней нет по определению (только скрипт
    # перехода). Любой «выловленный» текст здесь — мусор из head/скриптов.
    is_redirect = meta.get("topic-type", "").lower() == "redirect"
    if is_redirect:
        text = ""
        redirect_to = find_redirect_target(html) or redirect_to
    else:
        # у обычной статьи ссылки на другие темы — не редирект
        redirect_to = ""

    return {
        "title": title,
        "text": text,
        "html": html,
        "meta": meta,
        "topic_type": meta.get("topic-type", "").lower(),
        "redirect_to": redirect_to,
    }


# --------------------------------------------------------------------------
# 6. Эвристики для дерева справки
# --------------------------------------------------------------------------
def looks_like_help_root(path: Path) -> bool:
    """Похоже ли, что внутри лежит установленная справка (files/ + scripts/)."""
    try:
        names = {p.name.lower() for p in path.iterdir() if p.is_dir()}
    except OSError:
        return False
    return bool(names & {"files", "wrapped-files", "scripts"})


GENERIC_TITLES = {"", "help", "powermill help", "powermill", "index", "document",
                  "справка", "справка powermill", "untitled"}


def is_generic_title(title: str, path: Path | None = None) -> bool:
    """Заголовок «никакой»: пусто, имя файла-заглушки или типовой шаблон.

    Такие заголовки нужно заменять на название из оглавления.
    """
    t = (title or "").strip()
    if t.lower() in GENERIC_TITLES:
        return True
    if len(t) < 3:
        return True
    if path is not None:
        stem = path.stem.lower()
        if t.lower() in {stem, path.name.lower()}:
            return True
        if re.fullmatch(r"(guid|ctx|topichead)[-_.\w]*", t, re.I):
            return True
    return False


def is_junk_page(text: str, title: str = "") -> bool:
    """Пустые/служебные страницы: «404», пустые заголовки, только навигация."""
    body = text.strip()
    if len(body) < 40:
        return True
    junk_titles = {"search", "index", "default", "toc", "frameset", "blank", "empty"}
    if title.strip().lower() in junk_titles and len(body) < 200:
        return True
    return False

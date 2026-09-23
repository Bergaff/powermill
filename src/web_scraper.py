"""
Скраббер онлайн-справки PowerMill 2026 (help.autodesk.com).

BFS-обход статей по ссылкам ?guid=..., текст сохраняется
в output/parsed_web.txt (тем же форматом, что pdf/html-парсеры).

Против 403 (бот-защита Autodesk) использует curl_cffi
имитацию TLS-отпечатка Chrome; без него — обычный requests.

Запуск:  python -m src.web_scraper
Стоп:    Ctrl+C (прогресс сохраняется, при следующем запуске продолжит)
"""
import json
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    OUTPUT_DIR,
    WEB_HELP_BASE,
    WEB_HELP_DELAY,
    WEB_HELP_MAX_PAGES,
    WEB_HELP_SEEDS,
    WEB_HELP_TIMEOUT,
)

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CFFI = False

try:
    import requests as py_requests
except ImportError:
    py_requests = None

OUTPUT_FILE = OUTPUT_DIR / "parsed_web.txt"
STATE_FILE = OUTPUT_DIR / "web_scrape_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://help.autodesk.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}

GUID_RE = re.compile(r"guid=([A-Za-z0-9\-_%.]+)")

FOOTER_MARKERS = (
    "Was this information helpful",
    "Sign In to Autodesk",
    "Share this page",
)


def _page_url(guid: str | None) -> str:
    if not guid:
        return WEB_HELP_BASE
    return f"{WEB_HELP_BASE}?guid={guid}"


def fetch(url: str, timeout: int) -> tuple[str | None, int]:
    """Возвращает (html|None, status_code)."""
    if HAS_CFFI:
        try:
            resp = cffi_requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                impersonate="chrome",
                allow_redirects=True,
            )
            code = resp.status_code
            if code == 403:
                print("  ⚠ HTTP 403 даже с impersonate Chrome")
            if code != 200:
                print(f"  ⚠ HTTP {code}: {url}")
                return None, code
            return resp.text, code
        except Exception as e:
            print(f"  ⚠ curl_cffi ошибка: {e}")
            return None, 0

    if py_requests is None:
        print("  ⚠ Ни curl_cffi, ни requests не установлены: pip install curl_cffi requests")
        return None, 0
    try:
        resp = py_requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            print(f"  ⚠ HTTP {resp.status_code}: {url}")
            return None, resp.status_code
        return resp.text, resp.status_code
    except py_requests.RequestException as e:
        print(f"  ⚠ Ошибка сети: {e}")
        return None, 0


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        return re.sub(r"\s*\|\s*Autodesk\s*$", "", t)
    return "Untitled"


def extract_content_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for sel in (
        "header", "footer", "nav",
        "#sidebar", ".sidebar", "#nav", ".nav",
        ".share", ".feedback", ".helpful",
        ".cookies", "#cookies",
    ):
        for el in soup.select(sel):
            el.decompose()

    node = None
    for sel in (
        "article", "main", "#content", ".content",
        ".topic", ".article-content", "#body", "body",
    ):
        found = soup.select_one(sel)
        if found is not None and len(found.get_text(strip=True)) > 200:
            node = found
            break
    if node is None:
        node = soup

    text = node.get_text("\n")
    for marker in FOOTER_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]

    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def discover_guids(html: str, base_url: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r'''(?:href|data-href)=["']([^"']*\?guid=[^"']+)["']''', html):
        gm = GUID_RE.search(urljoin(base_url, m.group(1)))
        if gm:
            found.append(gm.group(1))
    for m in GUID_RE.finditer(html):
        found.append(m.group(1))
    seen: set[str] = set()
    ordered: list[str] = []
    for g in found:
        if g not in seen:
            seen.add(g)
            ordered.append(g)
    return ordered


def load_state() -> tuple[set[str], int]:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return set(state.get("visited", [])), int(state.get("good", 0))
        except Exception:
            pass
    return set(), 0


def save_state(visited: set[str], good: int) -> None:
    STATE_FILE.write_text(
        json.dumps({"visited": sorted(visited), "good": good}, ensure_ascii=False),
        encoding="utf-8",
    )


def crawl() -> int:
    visited, already_good = load_state()
    # Если ни одной статьи не вытащили (все 403 и т.п.) — начинаем с чистого листа,
    # иначе сиды будут считаться «посещёнными» и повторный запуск не даст ничего.
    if already_good == 0:
        if visited:
            print(f"♻ Прошлый запуск не дал статей (visited={len(visited)}) — сбрасываю состояние")
        visited = set()
        if STATE_FILE.exists():
            try:
                STATE_FILE.unlink()
            except OSError:
                pass

    queue: deque[str | None] = deque()

    for seed in WEB_HELP_SEEDS:
        if seed not in visited:
            queue.append(seed)
    if "HOME" not in visited:
        queue.append(None)

    if visited:
        print(f"↻ Возобновление: уже посещено {len(visited)}, статей {already_good}")

    mode_append = bool(visited) and OUTPUT_FILE.exists() and already_good > 0
    good = already_good if mode_append else 0
    wrote_any = mode_append

    engine = "curl_cffi (Chrome impersonate)" if HAS_CFFI else "requests (без impersonate)"
    print(f"🌐 База: {WEB_HELP_BASE}")
    print(f"   HTTP-движок: {engine}")
    print(f"   Лимит страниц: {WEB_HELP_MAX_PAGES}, пауза: {WEB_HELP_DELAY}s")
    if not HAS_CFFI:
        print("   ⚠ Рекомендуется: pip install curl_cffi  (обход 403)")

    consecutive_403 = 0
    pbar = tqdm(total=WEB_HELP_MAX_PAGES, initial=len(visited), desc="Скрапинг",
                unit="pg", position=0)

    try:
        while queue and len(visited) < WEB_HELP_MAX_PAGES:
            guid = queue.popleft()
            key = guid or "HOME"
            if key in visited:
                continue

            url = _page_url(guid)
            html, status = fetch(url, WEB_HELP_TIMEOUT)

            if status == 403:
                consecutive_403 += 1
                visited.add(key)
                if consecutive_403 >= 3:
                    print("\n🛑 Трижды HTTP 403 подряд — Autodesk блокирует скрапинг.")
                    print("   Фиксы (по порядку):")
                    print("   1) pip install curl_cffi   (если ещё не стоит)")
                    print("   2) del E:\\powermill-ai\\output\\web_scrape_state.json  и повтори")
                    print("   3) Поставь Оффлайн-справку:")
                    print("      https://www.autodesk.com/powermill-2026-help-download-enu")
                    print("      затем scripts\\find_help.bat + POWERMILL_HELP_DIR")
                    break
                save_state(visited, good)
                pbar.update(1)
                time.sleep(max(WEB_HELP_DELAY, 2.0))
                continue
            consecutive_403 = 0
            visited.add(key)

            if html:
                soup = BeautifulSoup(html, "html.parser")
                title = extract_title(soup)
                text = extract_content_text(soup)

                if len(text) > 300 and "guid" in html:
                    write_mode = "a" if wrote_any else "w"
                    with open(OUTPUT_FILE, write_mode, encoding="utf-8") as f:
                        f.write(f"\n{'=' * 60}\n")
                        f.write(f"Источник: {key} | Заголовок: {title}\n")
                        f.write(f"URL: {url}\n")
                        f.write(f"{'=' * 60}\n")
                        f.write(text + "\n")
                    wrote_any = True
                    good += 1
                    for new_guid in discover_guids(html, url):
                        if new_guid not in visited:
                            queue.append(new_guid)
                else:
                    print(f"  ⚠ Пустая/SPA-страница ({len(text)} симв.): {key}")

            save_state(visited, good)
            pbar.update(1)
            pbar.set_postfix(good=good, queue=len(queue))
            time.sleep(WEB_HELP_DELAY)

    except KeyboardInterrupt:
        print("\n⏸ Остановлено — прогресс сохранён.")
    finally:
        pbar.close()
        save_state(visited, good)

    print(f"\n✅ Скачано статей: {good} (посещено URL: {len(visited)})")
    print(f"💾 {OUTPUT_FILE}")
    if good == 0:
        print(
            "⚠ Текст не извлечён. См. сообщения выше (403 / SPA).\n"
            "  Оффлайн-справка: https://www.autodesk.com/powermill-2026-help-download-enu"
        )
    return good


if __name__ == "__main__":
    crawl()

"""
Скраббер онлайн-справки PowerMill 2026 (help.autodesk.com).

Стратегия запроса к каждой статье:
  1. Прямой запрос (curl_cffi impersonate Chrome) — быстро.
  2. При 403/ошибке — зеркало Wayback Machine (web.archive.org),
     контент берётся идентичным оригиналу (suffix id_).

Текст сохраняется в output/parsed_web.txt.

Запуск:  python -m src.web_scraper
Стоп:    Ctrl+C (прогресс сохраняется; при good=0 состояние сбрасывается)
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
    WEB_HELP_WAYBACK,
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
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://help.autodesk.com/",
}

GUID_RE = re.compile(r"guid=([A-Za-z0-9\-_%.]+)")

FOOTER_MARKERS = (
    "Was this information helpful",
    "Sign In to Autodesk",
    "Share this page",
)

WAYBACK_PREFIX = "https://web.archive.org/web/2025id_/"


def _page_url(guid: str | None) -> str:
    if not guid:
        return WEB_HELP_BASE
    return f"{WEB_HELP_BASE}?guid={guid}"


def _http_get(url: str, timeout: int) -> tuple[str | None, int]:
    if HAS_CFFI:
        try:
            resp = cffi_requests.get(
                url, headers=HEADERS, timeout=timeout,
                impersonate="chrome", allow_redirects=True,
            )
            return (resp.text if resp.status_code == 200 else None), resp.status_code
        except Exception:
            return None, 0
    if py_requests is None:
        return None, 0
    try:
        resp = py_requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return (resp.text if resp.status_code == 200 else None), resp.status_code
    except Exception:
        return None, 0


def fetch(url: str, timeout: int) -> tuple[str | None, int, str]:
    """-> (html|None, last_status, via).

    Цепочка:
      1) прямой запрос help.autodesk.com
      2) Wayback Machine (web.archive.org ... id_)
      3) для view/?guid= — попытка static cloudhelp ReferenceHelp не нужна:
         guid не конвертируется без индекса, см. Wayback.
    """
    html, code = _http_get(url, timeout)
    if html is not None:
        return html, 200, "direct"

    if WEB_HELP_WAYBACK and code in (403, 404, 429, 451, 0, 503):
        wb = WAYBACK_PREFIX + url
        print(f"  ↪ Wayback fallback ({code}): {url}")
        whtml, wcode = _http_get(wb, timeout)
        if whtml is not None:
            return whtml, 200, "wayback"
        # запасной снимок: любая доступная дата
        wb2 = "https://web.archive.org/web/2id_/" + url
        whtml2, wcode2 = _http_get(wb2, timeout)
        if whtml2 is not None:
            return whtml2, 200, "wayback2"
        print(f"  ⚠ Wayback не дал контент (HTTP {wcode or wcode2})")
        return None, code, "fail"

    print(f"  ⚠ HTTP {code}: {url}")
    return None, code, "fail"


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        return re.sub(r"\s*\|\s*Autodesk\s*$", "", t)
        # wayback title often prefixed with "Wayback Machine"
    return "Untitled"


def extract_content_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for sel in (
        "header", "footer", "nav",
        "#sidebar", ".sidebar", "#nav", ".nav",
        ".share", ".feedback", ".helpful",
        ".cookies", "#cookies", "#wm-ipp-base", "#wm-ipp",
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

    # вычистить хвост Wayback-обвязки
    for marker in ("Wayback Machine", "archive.org", "SAVE PAGE NOW"):
        idx = text.find(marker)
        if 0 < idx < 400:
            text = text[idx + len(marker):]

    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def discover_guids(html: str, base_url: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r'''(?:href|data-href)=["']([^"']*\?guid=[^"']+)["']''', html):
        gm = GUID_RE.search(m.group(1))
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
    if already_good == 0:
        if visited:
            print(f"♻ Прошлый запуск не дал статей — сбрасываю состояние")
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
        print(f"↻ Возобновление: посещено {len(visited)}, статей {already_good}")

    mode_append = bool(visited) and OUTPUT_FILE.exists() and already_good > 0
    good = already_good if mode_append else 0
    wrote_any = mode_append

    engine = "curl_cffi (Chrome)" if HAS_CFFI else "requests"
    wb = "on" if WEB_HELP_WAYBACK else "off"
    print(f"🌐 База: {WEB_HELP_BASE}")
    print(f"   Движок: {engine} | Wayback fallback: {wb}")
    print(f"   Лимит: {WEB_HELP_MAX_PAGES} стр., пауза {WEB_HELP_DELAY}s")

    consecutive_fail = 0
    pbar = tqdm(total=WEB_HELP_MAX_PAGES, initial=len(visited),
                desc="Скрапинг", unit="pg", position=0)

    try:
        while queue and len(visited) < WEB_HELP_MAX_PAGES:
            guid = queue.popleft()
            key = guid or "HOME"
            if key in visited:
                continue

            url = _page_url(guid)
            html, status, via = fetch(url, WEB_HELP_TIMEOUT)

            if html is None:
                visited.add(key)
                if status in (403, 451):
                    consecutive_fail += 1
                    if consecutive_fail >= 3 and not WEB_HELP_WAYBACK:
                        print("\n🛑 403 подряд без Wayback.")
                        break
                    if consecutive_fail >= 5:
                        print("\n🛑 Прямые запросы и Wayback не работают.")
                        print("   Ставь Оффлайн-справку:")
                        print("   https://www.autodesk.com/powermill-2026-help-download-enu")
                        break
                else:
                    consecutive_fail = 0
                save_state(visited, good)
                pbar.update(1)
                time.sleep(max(WEB_HELP_DELAY, 1.5))
                continue

            consecutive_fail = 0
            visited.add(key)
            soup = BeautifulSoup(html, "html.parser")
            title = extract_title(soup)
            text = extract_content_text(soup)

            # иногда wayback отдаёт 404-страницу архива
            if "404" in title or "Page cannot be found" in text[:200]:
                print(f"  ⚠ Нет снимка в Wayback: {key}")
                save_state(visited, good)
                pbar.update(1)
                time.sleep(WEB_HELP_DELAY)
                continue

            if len(text) > 300:
                write_mode = "a" if wrote_any else "w"
                with open(OUTPUT_FILE, write_mode, encoding="utf-8") as f:
                    f.write(f"\n{'=' * 60}\n")
                    f.write(f"Источник: {key} | Заголовок: {title}\n")
                    f.write(f"URL: {url} | via: {via}\n")
                    f.write(f"{'=' * 60}\n")
                    f.write(text + "\n")
                wrote_any = True
                good += 1
                for new_guid in discover_guids(html, url):
                    if new_guid not in visited:
                        queue.append(new_guid)
            else:
                print(f"  ⚠ Пустая страница ({len(text)}): {key}")

            save_state(visited, good)
            pbar.update(1)
            pbar.set_postfix(good=good, queue=len(queue), via=via)
            time.sleep(WEB_HELP_DELAY)

    except KeyboardInterrupt:
        print("\n⏸ Остановлено — прогресс сохранён.")
    finally:
        pbar.close()
        save_state(visited, good)

    print(f"\n✅ Статей: {good} (посещено URL: {len(visited)})")
    print(f"💾 {OUTPUT_FILE}")
    if good == 0:
        print(
            "⚠ Пусто. Ставь Оффлайн-справку (надёжно):\n"
            "  https://www.autodesk.com/powermill-2026-help-download-enu\n"
            "  scripts\\find_help.bat + POWERMILL_HELP_DIR + start_night_indexing.bat"
        )
    return good


if __name__ == "__main__":
    crawl()

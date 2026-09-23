"""
Скраббер онлайн-справки PowerMill 2026 (help.autodesk.com).

BFS-обход статей по ссылкам ?guid=..., текст сохраняется
в output/parsed_web.txt (тем же форматом, что pdf/html-парсеры).

Запуск:  python -m src.web_scraper
Стоп:    Ctrl+C (прогресс сохраняется, при следующем запуске продолжит)
"""
import json
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
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

OUTPUT_FILE = OUTPUT_DIR / "parsed_web.txt"
STATE_FILE = OUTPUT_DIR / "web_scrape_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "PowerMillAI-KB/1.0 (+personal knowledge base)"
    )
}

GUID_RE = re.compile(r"guid=([A-Za-z0-9\-_%.]+)")

# Мусорные надписи в конце каждой статьи
FOOTER_MARKERS = (
    "Was this information helpful",
    "Sign In to Autodesk",
    "Share this page",
)


def _page_url(guid: str | None) -> str:
    if not guid:
        return WEB_HELP_BASE
    return f"{WEB_HELP_BASE}?guid={guid}"


def _guid_from_url(url: str) -> str | None:
    m = GUID_RE.search(url)
    return m.group(1) if m else None


def fetch(url: str, timeout: int) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            print(f"  ⚠ HTTP {resp.status_code}: {url}")
            return None
        return resp.text
    except requests.RequestException as e:
        print(f"  ⚠ Ошибка сети: {e}")
        return None


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        t = re.sub(r"\s*\|\s*Autodesk\s*$", "", t)
        return t
    return "Untitled"


def extract_content_text(soup: BeautifulSoup) -> str:
    """Убираем хром (навигацию/подвал) и вытаскиваем тело статьи."""
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
        "article",
        "main",
        "#content",
        ".content",
        ".topic",
        ".article-content",
        "#body",
        "body",
    ):
        found = soup.select_one(sel)
        if found is not None and len(found.get_text(strip=True)) > 200:
            node = found
            break
    if node is None:
        node = soup

    text = node.get_text("\n")

    # Обрезать мусорный хвост статьи
    for marker in FOOTER_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]

    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def discover_guids(html: str, base_url: str) -> list[str]:
    """Все guid-ссылки со страницы (навигация + тело)."""
    found = []
    for m in re.finditer(r'''(?:href|data-href)=["']([^"']*\?guid=[^"']+)["']''', html):
        guid = _guid_from_url(urljoin(base_url, m.group(1)))
        if guid:
            found.append(guid)
    for m in GUID_RE.finditer(html):
        found.append(m.group(1))
    # дедуп, сохраняя порядок
    seen = set()
    ordered = []
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
    queue: deque[str | None] = deque()

    for seed in WEB_HELP_SEEDS:
        if seed not in visited:
            queue.append(seed)
    if "HOME" not in visited:
        queue.append(None)  # главная без guid

    if visited:
        print(f"↻ Возобновление: уже посещено {len(visited)}, статей {already_good}")

    # Дозапись при продолжении
    mode = "a" if visited and OUTPUT_FILE.exists() else "w"
    good = already_good if mode == "a" else 0

    print(f"🌐 База: {WEB_HELP_BASE}")
    print(f"   Лимит страниц: {WEB_HELP_MAX_PAGES}, пауза: {WEB_HELP_DELAY}s")

    pbar = tqdm(total=WEB_HELP_MAX_PAGES, initial=len(visited), desc="Скрапинг",
                unit="pg", position=0)

    try:
        while queue and len(visited) < WEB_HELP_MAX_PAGES:
            guid = queue.popleft()
            key = guid or "HOME"
            if key in visited:
                continue

            url = _page_url(guid)
            html = fetch(url, WEB_HELP_TIMEOUT)
            visited.add(key)

            if html:
                soup = BeautifulSoup(html, "html.parser")
                title = extract_title(soup)
                text = extract_content_text(soup)

                # SPA-оболочка без текста — считаем неудачей, но guid уже «посещён»
                if len(text) > 300 and "guid" in html:
                    with open(OUTPUT_FILE, "a" if mode == "a" or good else "w",
                              encoding="utf-8") as f:
                        f.write(f"\n{'=' * 60}\n")
                        f.write(f"Источник: {key} | Заголовок: {title}\n")
                        f.write(f"URL: {url}\n")
                        f.write(f"{'=' * 60}\n")
                        f.write(text + "\n")
                    good += 1
                    # открыть новые guid-ссылки
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
            "⚠ Не извлечён текст. Возможно help.autodesk.com отдаёт SPA-оболочку.\n"
            "  Тогда ставь Оффлайн-справку: https://www.autodesk.com/powermill-2026-help-download-enu\n"
            "  и укажи POWERMILL_HELP_DIR на её папку (найти: scripts\\find_help.bat)."
        )
    return good


if __name__ == "__main__":
    crawl()

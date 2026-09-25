"""
Разбор оглавления оффлайн-справки PowerMill (scripts/toc-treedata*.js).

Файл оглавления — это JS-объект вида:

    $(document).trigger("register-toc-data", ["", [
    {data:"Новые возможности", attr:{id:"d1e1569", tn:1, href:"./files/topichead.htm", ...}, children:[
    {data:"Новые возможности PowerMill 2026", attr:{..., href:"./files/GUID-222C...htm", rel:"page"}}]},
    ...

Отсюда берём:
  * человеческие заголовки страниц (в самих .htm их обычно нет);
  * иерархию (breadcrumb) — «Новые возможности > Новые возможности PowerMill 2026»;
  * порядок тем — он же нужен для структуры базы знаний.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.help_extract import unescape_js

# {data:"...", attr:{id:"d1e1516", tn:0, ..., href:"./files/x.htm", desc:""}
_NODE_RE = re.compile(r'\{data:"((?:[^"\\]|\\.)*)"\s*,\s*attr:\{', re.S)
_ATTR_RE = re.compile(r'(\w+)\s*:\s*(?:"((?:[^"\\]|\\.)*)"|(-?\d+)|(undefined|null|true|false))')


def normalize_href(href: str) -> str:
    """'./files/GUID-1.htm' / 'files\\GUID-1.htm' -> 'files/guid-1.htm'."""
    h = (href or "").strip().replace("\\", "/")
    h = re.sub(r"^\./+", "", h)
    h = h.split("#")[0]
    return h.lower()


def _parse_attrs(chunk: str) -> dict:
    attrs: dict[str, str] = {}
    for key, sval, nval, kword in _ATTR_RE.findall(chunk):
        if sval:
            attrs[key] = unescape_js(sval)
        elif nval:
            attrs[key] = nval
        elif kword not in ("undefined", "null"):
            attrs[key] = kword
    return attrs


def parse_toc_js(text: str) -> list[dict]:
    """Список узлов оглавления с глубиной: [{title, href, depth, path, id, ...}].

    `path` — цепочка родителей + сам узел (для breadcrumb):
        ["Стратегии обработки", "Чистовая обработка по кривой"]
    """
    nodes: list[dict] = []
    parents: dict[int, str] = {}   # глубина -> заголовок открытого узла
    depth = 0
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            quote = ch
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    break
                j += 1
            i = j + 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch == "[":
            depth += 1
            i += 1
            continue
        if ch == "]":
            depth = max(0, depth - 1)
            parents = {k: v for k, v in parents.items() if k <= depth}
            i += 1
            continue
        if ch == "{":
            m = _NODE_RE.match(text, i)
            if m:
                # границы attr:{...}
                brace = text.find("{", m.end() - 1)
                end = text.find("}", brace)
                attrs = _parse_attrs(text[brace:end if end > 0 else m.end() + 400])
                title = unescape_js(m.group(1))
                # родители — только узлы ВЫШЕ текущей глубины
                path = [parents[k] for k in sorted(parents) if k < depth]
                parents = {k: v for k, v in parents.items() if k < depth}
                parents[depth] = title
                nodes.append({
                    "title": title,
                    "href": attrs.get("href", ""),
                    "id": attrs.get("id", ""),
                    "rel": attrs.get("rel", ""),
                    "desc": attrs.get("desc", ""),
                    "depth": depth,
                    "path": [*path, title],
                })
                # переносим курсор за attr:{...} (children:[ останутся позади)
                i = (end + 1) if end > 0 else m.end()
                continue
        i += 1
    return nodes


def find_toc_files(root: Path) -> list[Path]:
    """Все toc-treedata*.js в дереве справки."""
    found: list[Path] = []
    for pattern in ("toc-treedata*.js", "toc*.js", "**/toc-treedata*.js"):
        found.extend(sorted(root.glob(pattern)))
    seen: set[Path] = set()
    out: list[Path] = []
    for f in found:
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        out.append(f)
    return out


def build_toc_map(nodes: list[dict]) -> dict[str, dict]:
    """href -> {title, breadcrumb, depth, toc_index, order}."""
    toc: dict[str, dict] = {}
    for order, node in enumerate(nodes):
        href = normalize_href(node.get("href", ""))
        if not href or href.endswith(".js"):
            continue
        crumb = [p for p in node["path"][:-1] if p]
        entry = {
            "title": node["title"],
            "breadcrumb": crumb,
            "depth": node["depth"],
            "order": order,
            "is_page": node.get("rel") == "page",
        }
        # topichead.htm и прочие не-страницы в карте не нужны, но пусть будут
        toc.setdefault(href, entry)
    return toc


def load_toc(roots: list[Path]) -> tuple[dict[str, dict], list[dict]]:
    """Читает оглавление из всех корней справки: (карта href->запись, узлы)."""
    toc_map: dict[str, dict] = {}
    all_nodes: list[dict] = []
    for root in roots:
        for js_path in find_toc_files(root):
            try:
                text = js_path.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                continue
            nodes = parse_toc_js(text)
            if not nodes:
                continue
            all_nodes.extend(nodes)
            for href, entry in build_toc_map(nodes).items():
                entry = dict(entry)
                entry["toc_file"] = str(js_path)
                toc_map.setdefault(href, entry)
    return toc_map, all_nodes


def toc_as_tree_text(nodes: list[dict], max_nodes: int = 0) -> str:
    """Человекочитаемое дерево оглавления (для отчёта)."""
    lines: list[str] = []
    base = min((int(n["depth"]) for n in nodes), default=0)
    for idx, node in enumerate(nodes):
        if max_nodes and idx >= max_nodes:
            lines.append(f"... (ещё {len(nodes) - max_nodes} узлов)")
            break
        indent = "  " * max(0, int(node["depth"]) - base)
        mark = "" if node.get("rel") == "page" else " [раздел]"
        href = f"  <- {node['href']}" if node.get("href") else ""
        lines.append(f"{indent}{node['title']}{mark}{href}")
    return "\n".join(lines)


def save_toc(toc_map: dict[str, dict], nodes: list[dict], output_dir: Path) -> tuple[Path, Path]:
    """Сохраняет help_toc.json (машинный) и help_toc.txt (человекочитаемый)."""
    json_path = output_dir / "help_toc.json"
    txt_path = output_dir / "help_toc.txt"
    json_path.write_text(
        json.dumps(toc_map, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    header = (
        "Дерево оглавления оффлайн-справки PowerMill\n"
        f"узлов: {len(nodes)}, страниц в карте: {len(toc_map)}\n"
        + "=" * 70 + "\n"
    )
    txt_path.write_text(header + toc_as_tree_text(nodes), encoding="utf-8")
    return json_path, txt_path


if __name__ == "__main__":  # быстрая проверка на одном файле: python -m src.toc_parser <файл>
    import sys

    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        parsed = parse_toc_js(p.read_text(encoding="utf-8", errors="replace"))
        print(f"узлов: {len(parsed)}")
        print(toc_as_tree_text(parsed, max_nodes=40))

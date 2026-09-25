"""
Веб-интерфейс ассистента (пункт 32) — чат в браузере, прогресс, отчёты.

Зачем: консольное меню хорошо для операций, но в нём не видно, что ассистент
делает прямо сейчас, и историю вопроса не полистать. Здесь то же самое ядро
(`src.pm_bridge.answer_request`), но:

* вопрос задаётся в поле ввода, ответы остаются в истории (можно листать);
* видно прогресс: строка за строкой — что делает ассистент (поиск по справке,
  обращение к модели, расчёт режимов) и сколько прошло времени;
* рядом отчёты (`output\\*.txt`) — читаются прямо в браузере, открываются в
  блокноте одной кнопкой;
* видно состояние PowerMill (живое чтение или снимок проекта) и итоги последних
  макросов (`STEP;…` из пунктов 30/31) — как список «что получилось».

Это тот же интерфейс, который потом встроится в панель плагина PowerMill
(WebView2), поэтому вся логика вынесена из HTML в Python-функции.
"""
from __future__ import annotations

from src import pml_files

import contextlib
import io
import json
import os
import re
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import OUTPUT_DIR
from src.pm_bridge import answer_request

# --------------------------------------------------------------------------
# Режимы (те же, что в макросе PM_AI_ASK и в меню чата)
# --------------------------------------------------------------------------
MODE_TITLES = {
    "ask": "Спросить",
    "macro": "Макрос PML",
    "error": "Разбор ошибки",
    "cutting": "Режимы резания",
}

# Человеческие названия отчётов (как в пункте 29)
REPORT_TITLES = {
    "pm_api_probe.txt": "Разведа API PowerMill (пункт 27)",
    "pm_link_report.txt": "Связь с PowerMill: установки, API, COM (пункт 23)",
    "pm_macros_report.txt": "Макросы внутри PowerMill (пункт 28)",
    "plugin_report.txt": "Каркас плагина PowerMill (пункт 25)",
    "project_context.json": "Снимок проекта (пункт 24)",
    "pm_edit_report.txt": "Запись режимов резания (пункт 30)",
    "pm_edit_result.txt": "Режимы: было → стало (макрос)",
    "pm_operation_report.txt": "Черновая операция (пункт 31)",
    "pm_operation_result.txt": "Операция: отчёт макроса по шагам",
    "pm_tool_report.txt": "Фреза в проекте: команды (пункт 33)",
    "pm_ribbon_report.txt": "Панель на ленте PowerMill (пункт 34)",
    "pm_check_report.txt": "Проверки траекторий (пункт 35)",
    "pm_check_result.txt": "Проверки: отчёт макроса",
    "pm_nc_report.txt": "NC-программа (пункт 36)",
    "pm_nc_result.txt": "NC: отчёт макроса",
    "pm_flow_report.txt": "«Делай»: поток целиком (шаг 3.6)",
    "pm_plugin_build_report.txt": "Сборка плагина (пункт 38)",
    "doctor_report.txt": "Проверка компьютера (пункт 40)",
    "pm_link_report.txt": "Связь с PowerMill (пункт 41)",
    "install_packages_report.txt": "Библиотеки: что стоит (пункт 43)",
    "data_root_report.txt": "Смена папки данных (пункт 42)",
    "vector_db_report.txt": "Векторная база (пункт 6)",
    "pm_tool_word.txt": "Слово создания фрезы",
    "pm_project.txt": "Снимок проекта от макроса",
    "pm_trace_1.txt": "Самопроверка моста: шаг 1 — файл записан",
    "pm_trace_2.txt": "Самопроверка моста: шаг 2 — файл прочитан",
    "pm_trace_3.txt": "Самопроверка моста: шаг 3 — запуск .bat",
    "pm_trace_4.txt": "Самопроверка моста: шаг 4 — пауза пройдена",
    "pm_trace_5.txt": "Самопроверка моста: шаг 5 — ответ программы",
    "pm_test.txt": "Тестовый файл моста",
    "bat_check.txt": "Проверка батников (пункт 26)",
    "pml_vocabulary.txt": "Словарь PML из справки",
    "OTCHET_DLYA_CHATA.txt": "Отчёт для чата (пункт 13)",
}

NAME_RE = re.compile(r"^(?:logs/)?[A-Za-z0-9_.\-]+$")
STEP_RE = re.compile(r"^STEP;([^;]*);([^;]*);(.*)$")
EDIT_RE = re.compile(r"^EDIT;([^;]*);([^;]*);([^;]*);([^;]*);([^;]*);(.*)$")
STATUS_MARK = {"ok": "✔", "fail": "✘", "skip": "•", "warn": "!"}


def _same_number(wanted: str, got: str, tolerance: float = 0.001) -> bool:
    """Совпадает ли записанное значение с тем, что хотели (0.1%, как в пункте 30)."""
    left, right = (wanted or "").strip(), (got or "").strip()
    if not left or not right:
        return False
    try:
        a, b = float(left), float(right)
    except ValueError:
        return left.lower() == right.lower()
    base = max(abs(a), 1e-9)
    return abs(a - b) <= abs(base) * tolerance

# Ответы считаются по очереди: и модель, и COM PowerMill не любят гонок,
# а технологу всё равно нужен один понятный поток прогресса.
RUN_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Задача (один вопрос) и её прогресс
# --------------------------------------------------------------------------
class Task:
    """Один вопрос технолога: текст, состояние, накопленный прогресс, ответ."""

    def __init__(self, task_id: int, query: str, mode: str):
        self.id = task_id
        self.query = query
        self.mode = mode
        self.state = "running"          # running | done | error
        self.progress: list[dict] = []
        self.answer = ""
        self.error = ""
        self.started = time.time()
        self.finished: float | None = None
        self.lock = threading.Lock()

    # ---------------- наполнение ----------------
    def note(self, text: str) -> None:
        """Строка прогресса (её видно в интерфейсе сразу)."""
        line = (text or "").strip()
        if not line:
            return
        with self.lock:
            if self.progress and self.progress[-1]["text"] == line:
                return                                   # не дублируем подряд
            self.progress.append({"t": round(time.time() - self.started, 1),
                                  "text": line})
            if len(self.progress) > 400:
                del self.progress[:100]

    def done(self, answer: str) -> None:
        with self.lock:
            self.answer = answer or ""
            self.state = "done"
            self.finished = time.time()
            self.progress.append({"t": round(self.finished - self.started, 1),
                                  "text": "Готово"})

    def fail(self, error: str) -> None:
        with self.lock:
            self.error = error or "неизвестная ошибка"
            self.state = "error"
            self.finished = time.time()
            self.progress.append({"t": round(self.finished - self.started, 1),
                                  "text": f"Ошибка: {self.error}"})

    # ---------------- вывод ----------------
    @property
    def seconds(self) -> float:
        end = self.finished or time.time()
        return round(end - self.started, 1)

    def as_dict(self) -> dict:
        with self.lock:
            progress = list(self.progress)
            state, answer, error = self.state, self.answer, self.error
        return {
            "id": self.id, "query": self.query, "mode": self.mode,
            "mode_title": MODE_TITLES.get(self.mode, self.mode),
            "state": state, "progress": progress, "answer": answer,
            "error": error, "seconds": self.seconds,
        }


class TaskStore:
    """Список задач: интерфейс забирает их по номеру (простой опрос)."""

    def __init__(self, runner=None, keep: int = 30):
        self.runner = runner or run_answer
        self.tasks: list[Task] = []
        self.keep = keep
        self.lock = threading.Lock()
        self.counter = 0

    def start(self, query: str, mode: str) -> Task:
        with self.lock:
            self.counter += 1
            task = Task(self.counter, query, mode)
            self.tasks.append(task)
            if len(self.tasks) > self.keep:
                self.tasks = self.tasks[-self.keep:]
        thread = threading.Thread(target=self._run, args=(task,), daemon=True)
        thread.start()
        return task

    def _run(self, task: Task) -> None:
        try:
            task.note("Жду очереди…" if RUN_LOCK.locked() else "Начинаю…")
            with RUN_LOCK:
                task.note("Ассистент думает…")
                answer = self.runner(task.query, task.mode, task.note)
            task.done(answer)
        except Exception as exc:                          # noqa: BLE001
            task.fail(f"{type(exc).__name__}: {exc}")

    def get(self, task_id: int) -> Task | None:
        with self.lock:
            for task in self.tasks:
                if task.id == task_id:
                    return task
        return None

    def latest(self) -> Task | None:
        with self.lock:
            return self.tasks[-1] if self.tasks else None

    def history(self, limit: int = 20) -> list[dict]:
        with self.lock:
            tasks = self.tasks[-limit:]
        return [t.as_dict() for t in tasks]


# --------------------------------------------------------------------------
# Сам ответ + живой прогресс
# --------------------------------------------------------------------------
class _StdoutTap(io.TextIOBase):
    """Ловит print() из глубины ассистента и превращает их в строки прогресса."""

    def __init__(self, note):
        super().__init__()
        self.note = note
        self.buffer = ""

    def write(self, text: str) -> int:
        self.buffer += text or ""
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.note(line)
        return len(text or "")

    def flush(self) -> None:
        if self.buffer.strip():
            self.note(self.buffer)
        self.buffer = ""


def run_answer(query: str, mode: str, note=None) -> str:
    """Считает ответ тем же движком, что чат и макрос PM_AI_ASK.

    Всё, что ассистент печатает по ходу дела, уходит в note() — это и есть
    прогресс в интерфейсе.
    """
    report = note or (lambda _text: None)
    tap = _StdoutTap(report)
    with contextlib.redirect_stdout(tap):
        answer = answer_request(query, mode, progress=report)
    tap.flush()
    return answer


# --------------------------------------------------------------------------
# Отчёты, проект, итоги макросов
# --------------------------------------------------------------------------
def _output_dir() -> Path:
    return Path(OUTPUT_DIR)


def safe_report_path(name: str) -> Path | None:
    """Имя файла из интерфейса -> путь внутри output (чужое не отдаём)."""
    name = (name or "").strip().replace("\\", "/")
    if not NAME_RE.match(name):
        return None
    if Path(name).name == "api_key.json":                  # ключ ИИ — не показываем
        return None
    base = _output_dir().resolve()
    path = (base / name).resolve()
    if base != path.parent and base not in path.parents:
        return None
    return path


def list_reports(limit: int = 40) -> list[dict]:
    """Файлы отчётов в output (свежие сверху) — как список пункта 29."""
    base = _output_dir()
    found: list[dict] = []
    for folder, prefix in ((base, ""), (base / "logs", "logs/")):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if not path.is_file() or path.name == "api_key.json":
                continue
            if path.suffix.lower() not in (".txt", ".json", ".log"):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            rel = f"{prefix}{path.name}"
            found.append({
                "name": rel,
                "title": REPORT_TITLES.get(path.name, path.name),
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m %H:%M"),
                "ts": stat.st_mtime,
            })
    found.sort(key=lambda item: item["ts"], reverse=True)
    return found[:limit]


def read_report(name: str) -> dict:
    path = safe_report_path(name)
    if path is None or not path.is_file():
        return {"name": name, "text": "", "error": "нет такого файла"}
    text = pml_files.decode(path.read_bytes())
    if len(text) > 200_000:
        text = text[:200_000] + "\n…(файл показан не весь)"
    return {"name": name, "text": text, "size": path.stat().st_size}


def open_report(name: str) -> dict:
    """Открыть отчёт в блокноте (как пункт 29) — только на Windows."""
    path = safe_report_path(name)
    if path is None or not path.is_file():
        return {"ok": False, "message": "нет такого файла"}
    if not hasattr(os, "startfile"):                       # Linux/macOS — песочница
        return {"ok": False, "message": f"открыть в блокноте можно только в Windows: {path}"}
    os.startfile(str(path))                                # type: ignore[attr-defined]
    return {"ok": True, "message": f"открываю: {path.name}"}


def project_lines() -> list[str]:
    """Состояние PowerMill: живое чтение COM, если получится, плюс снимок."""
    lines: list[str] = []
    try:
        from src import pm_com

        lines.extend(pm_com.status_lines())
    except Exception as exc:                               # noqa: BLE001
        lines.append(f"живое чтение недоступно: {exc}")

    snapshot = _output_dir() / "project_context.json"
    if snapshot.exists():
        try:
            data = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            stamp = datetime.fromtimestamp(snapshot.stat().st_mtime).strftime("%d.%m %H:%M")
            source = data.get("_source") or data.get("source") or "?"
            models = data.get("models") or data.get("model") or []
            if isinstance(models, str):
                models = [models]
            toolpaths = data.get("toolpaths") or []
            lines.append(f"снимок от {stamp}: {source}")
            lines.append(f"   модели: {', '.join(map(str, models)) or '—'}"
                         f" | траектории: {', '.join(map(str, toolpaths)) or '—'}")
    else:
        lines.append("снимка проекта нет (пункт 24 меню)")
    return lines


def refresh_project() -> list[str]:
    """Перечитать проект вживую и сохранить снимок (пункт 24)."""
    try:
        from src import pm_com

        _context, message = pm_com.refresh_context()
        return (message or "").splitlines() or ["готово"]
    except Exception as exc:                               # noqa: BLE001
        return [f"не получилось: {exc}"]


def recent_macro_steps(limit: int = 2) -> list[dict]:
    """Итоги последних макросов: строки STEP;… из пунктов 31 и 30."""
    titles: dict[str, str] = {}
    try:
        from src.pm_operation import STEP_TITLES

        titles = dict(STEP_TITLES)
    except Exception:                                      # noqa: BLE001
        pass

    result: list[dict] = []
    for filename, kind, title in (
        ("pm_operation_result.txt", "step", "Черновая операция (пункт 31)"),
        ("pm_edit_result.txt", "edit", "Режимы резания (пункт 30)"),
    ):
        path = _output_dir() / filename
        if not path.exists():
            continue
        rows: list[dict] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            match = STEP_RE.match(line)
            if match and kind == "step":
                step, status, rest = match.groups()
                rows.append({
                    "name": titles.get(step, step) or step,
                    "status": status if status in STATUS_MARK else "warn",
                    "text": rest.strip(),
                })
                continue
            match = EDIT_RE.match(line)
            if match and kind == "edit":
                toolpath, param, target, was, now, method = match.groups()
                ok = _same_number(target, now)
                rows.append({
                    "name": f"{toolpath} — {param}",
                    "status": "ok" if ok else "fail",
                    "text": f"{was.strip() or '?'} → {now.strip() or '?'}"
                            f" (нужно {target.strip()}, способ: {method.strip()})",
                })
        if rows:
            stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m %H:%M")
            result.append({"title": f"{title} — {stamp}", "file": filename,
                           "rows": rows[:20]})
    return result[:limit]


# --------------------------------------------------------------------------
# HTTP-сервер
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    """Маленький сервер: страница + несколько JSON-ручек."""

    server_version = "PowerMillAI"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):                     # тихо, без мусора
        pass

    # ---------------- утилиты ----------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload: dict | list, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    # ---------------- GET ----------------
    def do_GET(self):                                      # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path
        store: TaskStore = self.server.store                     # type: ignore[attr-defined]

        if path in ("/", "/index.html"):
            self._send(200, page_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if path == "/api/state":
            latest = store.latest()
            self._json({
                "running": bool(latest and latest.state == "running"),
                "task": latest.as_dict() if latest else None,
                "modes": [{"id": key, "title": title} for key, title in MODE_TITLES.items()],
            })
            return
        if path == "/api/task":
            raw = (query.get("id") or [""])[0]
            task = store.get(int(raw)) if raw.isdigit() else store.latest()
            if task is None:
                self._json({"error": "нет такой задачи"}, 404)
                return
            self._json(task.as_dict())
            return
        if path == "/api/history":
            self._json({"tasks": store.history()})
            return
        if path == "/api/reports":
            self._json({"reports": list_reports()})
            return
        if path == "/api/report":
            self._json(read_report((query.get("name") or [""])[0]))
            return
        if path == "/api/project":
            self._json({"lines": project_lines()})
            return
        if path == "/api/steps":
            self._json({"ops": recent_macro_steps()})
            return
        self._json({"error": "неизвестный адрес"}, 404)

    # ---------------- POST ----------------
    def do_POST(self):                                     # noqa: N802
        parsed = urlparse(self.path)
        store: TaskStore = self.server.store                     # type: ignore[attr-defined]
        data = self._body()

        if parsed.path == "/api/ask":
            text = str(data.get("text") or "").strip()
            mode = str(data.get("mode") or "ask").strip().lower()
            if mode not in MODE_TITLES:
                mode = "ask"
            if not text:
                self._json({"error": "пустой вопрос"}, 400)
                return
            task = store.start(text, mode)
            self._json({"id": task.id, "mode": task.mode}, 202)
            return
        if parsed.path == "/api/report/open":
            self._json(open_report(str(data.get("name") or "")))
            return
        if parsed.path == "/api/project/refresh":
            self._json({"lines": refresh_project()})
            return
        self._json({"error": "неизвестный адрес"}, 404)


def make_server(host: str = "127.0.0.1", port: int = 8765,
                store: TaskStore | None = None) -> ThreadingHTTPServer:
    """Готовый сервер (тесты передают свой store с поддельным движком)."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.store = store or TaskStore()                          # type: ignore[attr-defined]
    server.daemon_threads = True
    return server


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True,
          tries: int = 5) -> int:
    """Поднять интерфейс и работать, пока не закроют окно (Ctrl+C)."""
    server = None
    for attempt in range(tries):
        try:
            server = make_server(host, port + attempt)
            break
        except OSError as exc:
            print(f"⚠ Порт {port + attempt} занят ({exc}); пробую следующий…")
    if server is None:
        print(f"❌ Не удалось занять порты {port}…{port + tries - 1}.")
        return 1

    real_port = server.server_address[1]
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{shown}:{real_port}/"
    print("=" * 60)
    print("  🤖 PowerMill AI — интерфейс в браузере")
    print("=" * 60)
    print(f"  Адрес: {url}")
    print("  Это окно должно остаться открытым — в нём живёт интерфейс.")
    print("  Остановить: Ctrl+C в этом окне.")
    print("=" * 60)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:                           # noqa: BLE001
            print(f"  (браузер не открылся сам: {exc} — открой адрес вручную)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        server.server_close()
    return 0


# --------------------------------------------------------------------------
# Страница
# --------------------------------------------------------------------------
PAGE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>PowerMill AI — ассистент</title>
<style>
  :root {
    --bg: #12151b; --panel: #1a1f27; --panel2: #212733; --line: #2c3442;
    --text: #e6ebf2; --dim: #93a1b5; --user: #2a3f5f; --ai: #1d2430;
    --accent: #4d9cff; --ok: #4ad07a; --bad: #ff6b6b; --warn: #ffc861;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font: 15px/1.5 "Segoe UI", Roboto, Arial, sans-serif;
         background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }
  header { display: flex; align-items: center; gap: 12px; padding: 10px 16px;
           background: var(--panel); border-bottom: 1px solid var(--line); }
  header h1 { font-size: 17px; margin: 0; }
  .chip { font-size: 12px; padding: 3px 9px; border-radius: 11px;
          background: var(--panel2); color: var(--dim); border: 1px solid var(--line); }
  .chip.on { color: var(--ok); border-color: #2c5a3d; }
  .chip.off { color: var(--warn); }
  .spacer { flex: 1; }
  main { display: flex; height: calc(100vh - 49px); }
  .col { display: flex; flex-direction: column; min-width: 0; }
  #left { flex: 1; border-right: 1px solid var(--line); }
  #right { width: 380px; background: var(--panel); padding: 10px 12px; overflow-y: auto; }
  #chat { flex: 1; overflow-y: auto; padding: 14px 16px; }
  .msg { max-width: 900px; margin: 0 0 12px; padding: 10px 13px; border-radius: 10px;
         white-space: normal; word-wrap: break-word; }
  .msg.user { background: var(--user); margin-left: auto; }
  .msg.ai { background: var(--ai); border: 1px solid var(--line); }
  .msg .meta { font-size: 12px; color: var(--dim); margin-bottom: 5px; }
  .msg pre { background: #0e1218; border: 1px solid var(--line); border-radius: 8px;
             padding: 9px 11px; overflow-x: auto; white-space: pre-wrap; }
  .msg code { background: #0e1218; padding: 1px 4px; border-radius: 4px; }
  #progress { border-top: 1px solid var(--line); padding: 8px 16px; background: var(--panel); }
  #progress.hidden { display: none; }
  #ptitle { font-size: 13px; color: var(--dim); display: flex; gap: 8px; align-items: center; }
  #plines { max-height: 108px; overflow-y: auto; font: 12px/1.45 Consolas, monospace;
            color: var(--dim); margin: 5px 0 0; white-space: pre-wrap; }
  .bar { height: 3px; background: var(--panel2); border-radius: 2px; overflow: hidden; margin-top: 6px; }
  .bar i { display: block; height: 100%; width: 30%; background: var(--accent);
           animation: slide 1.1s linear infinite; }
  .bar.stop i { animation: none; width: 100%; background: var(--ok); }
  @keyframes slide { from { margin-left: -30%; } to { margin-left: 100%; } }
  #composer { border-top: 1px solid var(--line); padding: 10px 16px 14px; background: var(--panel); }
  #modes { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
  .mode { cursor: pointer; font-size: 13px; padding: 4px 11px; border-radius: 14px;
          border: 1px solid var(--line); background: var(--panel2); color: var(--dim); }
  .mode.sel { border-color: var(--accent); color: #fff; background: #23364d; }
  #row { display: flex; gap: 8px; align-items: flex-end; }
  #input { flex: 1; resize: vertical; min-height: 44px; max-height: 180px; padding: 10px 12px;
           border-radius: 9px; border: 1px solid var(--line); background: var(--panel2);
           color: var(--text); font: inherit; }
  button { cursor: pointer; border: 1px solid var(--line); background: var(--panel2);
           color: var(--text); border-radius: 8px; padding: 9px 14px; font: inherit; }
  button:hover { border-color: var(--accent); }
  button.primary { background: #2b5ea8; border-color: #2b5ea8; }
  button:disabled { opacity: .5; cursor: default; }
  h3 { font-size: 14px; margin: 4px 0 8px; color: var(--dim); text-transform: uppercase;
       letter-spacing: .5px; }
  .card { background: var(--panel2); border: 1px solid var(--line); border-radius: 9px;
          padding: 9px 11px; margin-bottom: 9px; }
  .rlist { max-height: 260px; overflow-y: auto; }
  .rline { display: flex; gap: 8px; padding: 5px 4px; border-bottom: 1px solid var(--line);
           cursor: pointer; font-size: 13px; }
  .rline:hover { background: #232b38; }
  .rline .nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rline .dt { color: var(--dim); font-size: 12px; }
  #viewer { margin-top: 8px; }
  #vtext { max-height: 300px; overflow: auto; white-space: pre-wrap; font: 12px/1.45 Consolas, monospace;
           background: #0e1218; border: 1px solid var(--line); border-radius: 8px; padding: 8px; }
  .step { display: flex; gap: 7px; font-size: 13px; padding: 3px 0; }
  .step .st { width: 16px; }
  .st.ok { color: var(--ok); } .st.fail { color: var(--bad); }
  .st.warn, .st.skip { color: var(--warn); }
  #plist div { font-size: 13px; padding: 2px 0; }
  .hint { font-size: 12px; color: var(--dim); }
  @media (max-width: 900px) { #right { display: none; } }
</style>
</head>
<body>
<header>
  <h1>🤖 PowerMill AI</h1>
  <span class="chip" id="chip-pm">PowerMill: …</span>
  <span class="chip" id="chip-run">готов</span>
  <span class="spacer"></span>
  <span class="hint">Enter — отправить, Shift+Enter — новая строка</span>
</header>

<main>
  <div class="col" id="left">
    <div id="chat"></div>

    <div id="progress" class="hidden">
      <div id="ptitle"><b id="pstate">Ассистент работает…</b><span id="ptime"></span></div>
      <div class="bar" id="pbar"><i></i></div>
      <pre id="plines"></pre>
    </div>

    <div id="composer">
      <div id="modes"></div>
      <div id="row">
        <textarea id="input" placeholder="Спроси про PowerMill, попроси макрос, посчитай режимы…"></textarea>
        <button class="primary" id="send">Спросить</button>
      </div>
    </div>
  </div>

  <div class="col" id="right">
    <h3>Отчёты</h3>
    <div class="card">
      <div class="rlist" id="reports"><span class="hint">читаю…</span></div>
      <div id="viewer">
        <div class="hint" id="vname">выбери файл — покажу содержимое</div>
        <pre id="vtext" style="display:none"></pre>
        <button id="vopen" style="display:none; margin-top:6px">Открыть в блокноте</button>
      </div>
    </div>

    <h3>Проект в PowerMill</h3>
    <div class="card">
      <div id="plist"><span class="hint">читаю…</span></div>
      <button id="prefresh" style="margin-top:6px">Обновить снимок проекта</button>
    </div>

    <h3>Последние операции</h3>
    <div class="card" id="steps"><span class="hint">пока ничего не запускалось</span></div>
  </div>
</main>

<script>
const MODES = __MODES__;
let mode = "ask", current = null, timer = null;

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function inline(text) {
  return esc(text)
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/^#{1,4}\s*(.*)$/gm, "<b>$1</b>")
    .replace(/\n/g, "<br>");
}
function md(text) {
  return String(text == null ? "" : text).split("```").map(function (part, i) {
    if (i % 2 === 1) {
      return "<pre>" + esc(part.replace(/^[a-zA-Z]*\n/, "")) + "</pre>";
    }
    return inline(part);
  }).join("");
}

function addMsg(role, text, meta) {
  const box = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "msg " + role;
  const head = meta ? '<div class="meta">' + esc(meta) + "</div>" : "";
  div.innerHTML = head + (role === "ai" ? md(text) : esc(text).replace(/\n/g, "<br>"));
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(res.status + " " + res.statusText);
  return await res.json();
}

function setChip(id, text, cls) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = "chip" + (cls ? " " + cls : "");
}

function buildModes() {
  const box = document.getElementById("modes");
  box.innerHTML = "";
  MODES.forEach(function (m) {
    const b = document.createElement("span");
    b.className = "mode" + (m.id === mode ? " sel" : "");
    b.textContent = m.title;
    b.onclick = function () { mode = m.id; buildModes(); };
    box.appendChild(b);
  });
}

function showProgress(title) {
  document.getElementById("progress").classList.remove("hidden");
  document.getElementById("pstate").textContent = title;
  document.getElementById("plines").textContent = "";
  document.getElementById("pbar").className = "bar";
  document.getElementById("send").disabled = true;
}

function hideProgress(done) {
  document.getElementById("pbar").className = "bar stop";
  document.getElementById("send").disabled = false;
  if (done) {
    setTimeout(function () {
      document.getElementById("progress").classList.add("hidden");
    }, 1200);
  }
}

function renderProgress(task) {
  const lines = document.getElementById("plines");
  const text = task.progress.map(function (p) { return p.t + "с  " + p.text; }).join("\n");
  if (lines.textContent !== text) {
    lines.textContent = text;
    lines.scrollTop = lines.scrollHeight;
  }
  document.getElementById("ptime").textContent = task.seconds + " с";
}

async function poll(id) {
  const task = await api("/api/task?id=" + id);
  renderProgress(task);
  if (task.state === "running") {
    document.getElementById("pstate").textContent = "Ассистент работает…";
    return;
  }
  clearInterval(timer); timer = null;
  if (task.state === "error") {
    document.getElementById("pstate").textContent = "Ошибка";
    addMsg("ai", "⚠ Не получилось: " + task.error, "ошибка · " + task.mode_title);
  } else {
    document.getElementById("pstate").textContent = "Готово за " + task.seconds + " с";
    addMsg("ai", task.answer, task.mode_title + " · " + task.seconds + " с");
  }
  setChip("chip-run", "готов");
  hideProgress(true);
  loadSteps();
}

async function send() {
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text || timer) return;
  input.value = "";
  addMsg("user", text, MODES.find(function (m) { return m.id === mode; }).title);
  setChip("chip-run", "работает…", "off");
  showProgress("Отправляю…");
  try {
    const res = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, mode: mode }),
    });
    current = res.id;
    poll(res.id);
    timer = setInterval(function () { poll(res.id); }, 700);
  } catch (e) {
    hideProgress(true);
    setChip("chip-run", "готов");
    addMsg("ai", "⚠ Не получилось отправить: " + e.message);
  }
}

async function loadHistory() {
  try {
    const data = await api("/api/history");
    if (!data.tasks.length) {
      addMsg("ai", "Здравствуй! Я ассистент PowerMill.\n\n" +
        "• «Спросить» — вопрос по документации и проекту\n" +
        "• «Макрос PML» — напишу макрос и проверю его словарь\n" +
        "• «Разбор ошибки» — что значит сообщение PowerMill\n" +
        "• «Режимы резания» — посчитаю S/F по формулам\n\n" +
        "Тяжёлые операции (запись режимов — пункт 30, черновая обработка — пункт 31)\n" +
        "по-прежнему запускаются батниками: они показывают каждую команду до выполнения.");
      return;
    }
    data.tasks.forEach(function (t) {
      addMsg("user", t.query, t.mode_title);
      addMsg("ai", t.state === "error" ? "⚠ " + t.error : t.answer,
             t.mode_title + " · " + t.seconds + " с");
    });
  } catch (e) { /* история не критична */ }
}

async function loadReports() {
  const box = document.getElementById("reports");
  try {
    const data = await api("/api/reports");
    if (!data.reports.length) { box.innerHTML = '<span class="hint">отчётов пока нет</span>'; return; }
    box.innerHTML = "";
    data.reports.forEach(function (r) {
      const div = document.createElement("div");
      div.className = "rline";
      div.innerHTML = '<span class="nm">' + esc(r.title) + '</span><span class="dt">' +
                      esc(r.mtime) + "</span>";
      div.onclick = function () { openFile(r.name); };
      box.appendChild(div);
    });
  } catch (e) { box.innerHTML = '<span class="hint">не получилось прочитать список</span>'; }
}

async function openFile(name) {
  const data = await api("/api/report?name=" + encodeURIComponent(name));
  document.getElementById("vname").textContent = name + (data.size ? " · " + data.size + " байт" : "");
  const pre = document.getElementById("vtext");
  pre.style.display = "block";
  pre.textContent = data.error ? data.error : data.text;
  const btn = document.getElementById("vopen");
  btn.style.display = "inline-block";
  btn.onclick = async function () {
    const res = await api("/api/report/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name }),
    });
    alert(res.message);
  };
}

async function loadProject(refresh) {
  const box = document.getElementById("plist");
  box.innerHTML = '<span class="hint">читаю…</span>';
  try {
    const data = refresh
      ? await api("/api/project/refresh", { method: "POST" })
      : await api("/api/project");
    box.innerHTML = "";
    (data.lines || []).forEach(function (line) {
      const div = document.createElement("div");
      div.textContent = line;
      box.appendChild(div);
    });
    const joined = (data.lines || []).join(" ");
    setChip("chip-pm", /жив|PowerMill \(COM\)/i.test(joined) ? "PowerMill: живой" : "PowerMill: снимок",
            /жив|PowerMill \(COM\)/i.test(joined) ? "on" : "off");
  } catch (e) {
    box.innerHTML = '<span class="hint">не получилось прочитать</span>';
  }
}

async function loadSteps() {
  const box = document.getElementById("steps");
  try {
    const data = await api("/api/steps");
    if (!data.ops.length) { box.innerHTML = '<span class="hint">пока ничего не запускалось</span>'; return; }
    box.innerHTML = "";
    data.ops.forEach(function (op) {
      const title = document.createElement("div");
      title.innerHTML = "<b>" + esc(op.title) + "</b>";
      box.appendChild(title);
      op.rows.forEach(function (row) {
        const div = document.createElement("div");
        div.className = "step";
        div.innerHTML = '<span class="st ' + esc(row.status) + '">' +
          (row.status === "ok" ? "✔" : row.status === "fail" ? "✘" : "•") + "</span><span>" +
          esc(row.name) + (row.text ? " — " + esc(row.text) : "") + "</span>";
        box.appendChild(div);
      });
      box.appendChild(document.createElement("div")).innerHTML = "&nbsp;";
    });
  } catch (e) { box.innerHTML = '<span class="hint">нет данных</span>'; }
}

document.getElementById("send").onclick = send;
document.getElementById("prefresh").onclick = function () { loadProject(true); };
document.getElementById("input").addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});

(async function start() {
  try {
    const state = await api("/api/state");
    if (state.modes && state.modes.length) {
      MODES.length = 0; state.modes.forEach(function (m) { MODES.push(m); });
    }
    buildModes();
    if (state.running && state.task) {
      current = state.task.id;
      setChip("chip-run", "работает…", "off");
      showProgress("Ассистент работает…");
      renderProgress(state.task);
      poll(current);
      timer = setInterval(function () { poll(current); }, 700);
    }
  } catch (e) { buildModes(); }
  loadHistory();
  loadReports();
  loadProject(false);
  loadSteps();
})();
</script>
</body>
</html>
"""


def page_html() -> str:
    """Страница с подставленными режимами (то же, что отдаёт сервер)."""
    modes = json.dumps([{"id": key, "title": title} for key, title in MODE_TITLES.items()],
                       ensure_ascii=False)
    return PAGE.replace("__MODES__", modes)


def main() -> int:                                         # pragma: no cover
    return serve()

"""
Тесты веб-интерфейса (пункт 32): страница, задачи с прогрессом, отчёты, ручки.

Никакого ИИ и PowerMill здесь нет: подставляем свой «движок ответа», чтобы
проверить, что интерфейс показывает прогресс и не падает на пустых данных.
"""
from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path

import pytest

from src import webui


# --------------------------------------------------------------------------
# страница и режимы
# --------------------------------------------------------------------------
def test_page_has_core_elements():
    page = webui.page_html()
    for marker in ('id="chat"', 'id="input"', 'id="send"', 'id="reports"',
                   'id="progress"', 'id="plines"', 'id="chip-pm"', 'id="steps"',
                   'id="plist"'):
        assert marker in page, f"нет элемента {marker}"


def test_page_has_modes_injected():
    page = webui.page_html()
    assert "__MODES__" not in page
    assert "Режимы резания" in page
    assert "Макрос PML" in page


def test_page_has_progress_and_back_help():
    """В интерфейсе должно быть видно, что происходит, и как вернуться."""
    page = webui.page_html()
    assert "Ассистент работает" in page
    assert "/api/history" in page          # история — можно листать назад
    assert "Enter" in page


# --------------------------------------------------------------------------
# задача и прогресс
# --------------------------------------------------------------------------
def test_task_notes_progress_and_deduplicates():
    task = webui.Task(1, "вопрос", "ask")
    task.note("шаг 1")
    task.note("шаг 1")      # повтор подряд не нужен
    task.note("")
    task.note("шаг 2")
    assert [p["text"] for p in task.progress] == ["шаг 1", "шаг 2"]
    assert task.state == "running"


def test_task_done_and_error_states():
    task = webui.Task(1, "вопрос", "ask")
    task.done("ответ")
    assert task.state == "done" and task.answer == "ответ"
    assert task.progress[-1]["text"] == "Готово"

    bad = webui.Task(2, "вопрос", "ask")
    bad.fail("ValueError: плохо")
    assert bad.state == "error" and "плохо" in bad.error


def test_store_runs_runner_with_progress():
    def runner(query, mode, note):
        note("ищу в справке")
        note("зову модель")
        return f"ответ на «{query}» в режиме {mode}"

    store = webui.TaskStore(runner=runner)
    task = store.start("как задать врезание", "ask")
    deadline = time.time() + 10
    while task.state == "running" and time.time() < deadline:
        time.sleep(0.02)

    assert task.state == "done"
    assert task.answer == "ответ на «как задать врезание» в режиме ask"
    texts = [p["text"] for p in task.progress]
    assert "ищу в справке" in texts and "зову модель" in texts and "Готово" in texts
    assert store.get(task.id) is task
    assert store.history()[0]["id"] == task.id


def test_store_turns_exception_into_error_state():
    def runner(query, mode, note):
        raise RuntimeError("нет модели")

    store = webui.TaskStore(runner=runner)
    task = store.start("вопрос", "ask")
    deadline = time.time() + 10
    while task.state == "running" and time.time() < deadline:
        time.sleep(0.02)
    assert task.state == "error"
    assert "нет модели" in task.error


def test_run_answer_cutting_mode_needs_no_ai(monkeypatch):
    """Режимы резания считаются формулами — прогресс и ответ без ИИ."""
    from src import cutting

    monkeypatch.setattr(cutting, "answer",
                        lambda query: ("S=4500, F=1200", {"rpm": 4500}))
    seen: list[str] = []
    answer = webui.run_answer("сталь 40Х фреза D16", "cutting", seen.append)
    assert answer == "S=4500, F=1200"
    assert any("формулам" in line for line in seen)


# --------------------------------------------------------------------------
# отчёты и итоги макросов
# --------------------------------------------------------------------------
@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "OUTPUT_DIR", tmp_path)
    return tmp_path


def test_list_reports_sorted_with_titles(out_dir):
    (out_dir / "pm_api_probe.txt").write_text("разведка", encoding="utf-8")
    (out_dir / "api_key.json").write_text('{"key": "секрет"}', encoding="utf-8")
    (out_dir / "чужой.docx").write_text("не отчёт", encoding="utf-8")

    names = [r["name"] for r in webui.list_reports()]
    assert names == ["pm_api_probe.txt"]
    assert webui.list_reports()[0]["title"].startswith("Разведа API")


def test_list_reports_includes_logs_folder(out_dir):
    logs = out_dir / "logs"
    logs.mkdir()
    (logs / "run.log").write_text("лог", encoding="utf-8")
    assert [r["name"] for r in webui.list_reports()] == ["logs/run.log"]


def test_safe_report_path_blocks_escape(out_dir):
    assert webui.safe_report_path("../secret.txt") is None
    assert webui.safe_report_path("C:/Windows/win.ini") is None
    assert webui.safe_report_path("api_key.json") is None
    assert webui.safe_report_path("pm_api_probe.txt") == out_dir / "pm_api_probe.txt"
    assert webui.safe_report_path("logs/run.log") == out_dir / "logs" / "run.log"


def test_read_report_and_missing(out_dir):
    (out_dir / "pm_project.txt").write_text("модель Деталь1", encoding="utf-8")
    data = webui.read_report("pm_project.txt")
    assert "Деталь1" in data["text"]
    assert webui.read_report("нет.txt")["error"]


def test_open_report_outside_windows(out_dir):
    (out_dir / "pm_project.txt").write_text("x", encoding="utf-8")
    result = webui.open_report("pm_project.txt")
    if hasattr(webui.os, "startfile"):
        assert result["ok"]
    else:
        assert not result["ok"] and "Windows" in result["message"]


def test_recent_macro_steps_reads_step_lines(out_dir):
    (out_dir / "pm_operation_result.txt").write_text(
        "STEP;tool_create;ok;создана фреза D16\n"
        "STEP;block;fail;заготовка не поднялась\n"
        "мусор\n", encoding="utf-8")
    ops = webui.recent_macro_steps()
    assert len(ops) == 1
    rows = ops[0]["rows"]
    assert rows[0]["status"] == "ok" and "фреза" in rows[0]["text"]
    assert rows[1]["status"] == "fail"


def test_recent_macro_steps_reads_edit_lines(out_dir):
    (out_dir / "pm_edit_result.txt").write_text(
        "EDIT;Chernovaya_D16;SpindleSpeed;4500;4500;4500;param\n"
        "EDIT;Chernovaya_D16;Feedrate.Cutting;1200;900;900;command\n",
        encoding="utf-8")
    ops = webui.recent_macro_steps()
    assert ops and ops[0]["file"] == "pm_edit_result.txt"
    assert [r["status"] for r in ops[0]["rows"]] == ["ok", "fail"]
    assert "нужно 1200" in ops[0]["rows"][1]["text"]


# --------------------------------------------------------------------------
# HTTP-ручки
# --------------------------------------------------------------------------
class Client:
    """Простой клиент к серверу интерфейса (без сторонних библиотек)."""

    def __init__(self, port: int):
        self.port = port

    def request(self, method: str, path: str, payload: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        answer = conn.getresponse()
        raw = answer.read()
        conn.close()
        return answer.status, raw


@pytest.fixture
def server(out_dir, monkeypatch):
    def runner(query, mode, note):
        note("думаю")
        return f"эхо: {query}"

    store = webui.TaskStore(runner=runner)
    srv = webui.make_server("127.0.0.1", 0, store=store)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield Client(srv.server_address[1])
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def test_http_serves_page(server):
    status, raw = server.request("GET", "/")
    assert status == 200
    assert "PowerMill AI" in raw.decode("utf-8")


def test_http_state_and_ask_round_trip(server):
    status, raw = server.request("GET", "/api/state")
    assert status == 200
    state = json.loads(raw)
    assert state["running"] is False and state["task"] is None
    assert [m["id"] for m in state["modes"]] == ["ask", "macro", "error", "cutting"]

    status, raw = server.request("POST", "/api/ask", {"text": "привет", "mode": "ask"})
    assert status == 202
    task_id = json.loads(raw)["id"]

    deadline = time.time() + 10
    while time.time() < deadline:
        _status, raw = server.request("GET", f"/api/task?id={task_id}")
        task = json.loads(raw)
        if task["state"] != "running":
            break
        time.sleep(0.05)

    assert task["state"] == "done"
    assert task["answer"] == "эхо: привет"
    assert [p["text"] for p in task["progress"]][:2] == ["Начинаю…", "Ассистент думает…"] or \
        "думаю" in [p["text"] for p in task["progress"]]


def test_http_ask_rejects_empty_and_unknown_mode(server):
    status, _raw = server.request("POST", "/api/ask", {"text": "   "})
    assert status == 400

    status, raw = server.request("POST", "/api/ask", {"text": "ок", "mode": "чужой"})
    assert status == 202
    assert json.loads(raw)["mode"] == "ask"


def test_http_reports_and_unknown_path(server, out_dir):
    (out_dir / "pm_link_report.txt").write_text("связь есть", encoding="utf-8")

    status, raw = server.request("GET", "/api/reports")
    assert status == 200
    assert json.loads(raw)["reports"][0]["name"] == "pm_link_report.txt"

    status, raw = server.request("GET", "/api/report?name=pm_link_report.txt")
    assert "связь есть" in json.loads(raw)["text"]

    status, _raw = server.request("GET", "/api/report?name=../secret.txt")
    assert status == 200 and json.loads(_raw)["error"]

    assert server.request("GET", "/api/nope")[0] == 404
    assert server.request("POST", "/api/nope")[0] == 404


def test_http_history_returns_tasks(server):
    server.request("POST", "/api/ask", {"text": "первый", "mode": "cutting"})
    deadline = time.time() + 10
    tasks: list = []
    while time.time() < deadline:
        _status, raw = server.request("GET", "/api/history")
        tasks = json.loads(raw)["tasks"]
        if tasks and tasks[0]["state"] != "running":
            break
        time.sleep(0.05)
    assert tasks and tasks[0]["query"] == "первый"


def test_http_project_and_steps_endpoints(server, out_dir):
    (out_dir / "pm_operation_result.txt").write_text(
        "STEP;toolpath;ok;траектория создана\n", encoding="utf-8")

    status, raw = server.request("GET", "/api/steps")
    assert status == 200
    ops = json.loads(raw)["ops"]
    assert ops and ops[0]["rows"][0]["name"]

    status, raw = server.request("GET", "/api/project")
    assert status == 200
    assert isinstance(json.loads(raw)["lines"], list)


def test_make_server_uses_default_store():
    srv = webui.make_server("127.0.0.1", 0)
    try:
        assert isinstance(srv.store, webui.TaskStore)          # type: ignore[attr-defined]
        assert srv.store.runner is webui.run_answer            # type: ignore[attr-defined]
    finally:
        srv.server_close()


def test_safe_report_path_rejects_empty(out_dir):
    assert webui.safe_report_path("") is None
    assert webui.safe_report_path("   ") is None
    assert webui.safe_report_path("папка/файл.txt") is None

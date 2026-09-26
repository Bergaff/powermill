"""
Тесты MCP-сервера (пункт 44) и подключения к ИИ-клиенту.

Проверяем без ИИ, без PowerMill и без клиента: сервер общается строками JSON, его
можно гонять как обычную функцию. Здесь то, что важно на живом компьютере:

* клиент видит инструменты и их схемы;
* всё, что печатают наши сценарии, не попадает в поток протокола;
* выполнить макрос без подтверждения нельзя, и только наши макросы;
* настройки клиента не перезаписываются молча (копия .bak, чужие серверы целы).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src import mcp_server

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def call(server: mcp_server.McpServer, message: dict) -> dict | None:
    """Прогоняет сообщение через сервер и разбирает ответ обратно."""
    answer = server.handle_line(json.dumps(message, ensure_ascii=False))
    return json.loads(answer) if answer else None


def call_tool(server: mcp_server.McpServer, tool: str, **arguments) -> dict:
    return call(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": tool, "arguments": arguments}})


# --------------------------------------------------------------------------
# Протокол: знакомство, список инструментов, служебные мелочи
# --------------------------------------------------------------------------
def test_initialize_answers_with_protocol_and_instructions():
    server = mcp_server.McpServer()
    answer = call(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05",
                                      "clientInfo": {"name": "тест"}}})
    result = answer["result"]
    assert result["protocolVersion"] == "2024-11-05"      # согласовали с клиентом
    assert result["serverInfo"]["name"] == mcp_server.SERVER_NAME
    assert result["capabilities"]["tools"]
    assert "powermill_run_macro" in result["instructions"]  # предупреждаем клиента


def test_initialize_with_unknown_version_answers_our_default():
    server = mcp_server.McpServer()
    answer = call(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "1999-01-01"}})
    assert answer["result"]["protocolVersion"] == mcp_server.DEFAULT_PROTOCOL


def test_notifications_get_no_answer():
    server = mcp_server.McpServer()
    assert server.handle({"jsonrpc": "2.0",
                          "method": "notifications/initialized"}) is None
    assert server.initialized is True


def test_ping_and_unknown_method():
    server = mcp_server.McpServer()
    assert call(server, {"jsonrpc": "2.0", "id": 1, "method": "ping"})["result"] == {}
    answer = call(server, {"jsonrpc": "2.0", "id": 2, "method": "чужой/метод"})
    assert answer["error"]["code"] == mcp_server.ERROR_METHOD


def test_broken_json_answers_with_parse_error_and_keeps_working():
    server = mcp_server.McpServer()
    answer = json.loads(server.handle_line("{это не json}"))
    assert answer["error"]["code"] == mcp_server.ERROR_PARSE
    # сервер жив: следующий запрос обрабатывается
    assert call(server, {"jsonrpc": "2.0", "id": 1, "method": "ping"})["result"] == {}


def test_tools_list_has_schemas_and_names():
    server = mcp_server.McpServer()
    tools = call(server, {"jsonrpc": "2.0", "id": 1,
                          "method": "tools/list"})["result"]["tools"]
    names = [item["name"] for item in tools]
    for expected in ("powermill_status", "powermill_cutting", "powermill_ask",
                     "powermill_error", "powermill_compare", "powermill_macro",
                     "powermill_plan_operation", "powermill_run_macro",
                     "powermill_read_report"):
        assert expected in names, expected
    cutting = next(item for item in tools if item["name"] == "powermill_cutting")
    assert cutting["inputSchema"]["required"] == ["request"]
    assert "детерминированный" in cutting["description"]


def test_unknown_tool_is_a_params_error_with_hint():
    server = mcp_server.McpServer()
    answer = call_tool(server, "нет_такого")
    assert answer["error"]["code"] == mcp_server.ERROR_PARAMS
    assert "powermill_cutting" in answer["error"]["message"]


def test_unknown_argument_is_refused():
    """"Лишний аргумент — почти всегда опечатка клиента; лучше сказать прямо."""
    server = mcp_server.McpServer()
    answer = call_tool(server, "powermill_cutting", request="Сталь 40Х", matereal="опечатка")
    assert answer["result"]["isError"] is True
    assert "matereal" in answer["result"]["content"][0]["text"]


# --------------------------------------------------------------------------
# Инструменты: считают и читают, ничего не меняя
# --------------------------------------------------------------------------
def test_cutting_tool_returns_real_numbers():
    server = mcp_server.McpServer()
    answer = call_tool(server, "powermill_cutting",
                       request="Сталь 40Х, фреза D16, черновая")
    text = answer["result"]["content"][0]["text"]
    assert "S (об/мин)" in text and "F (мм/мин)" in text
    assert answer["result"].get("isError") is not True


def test_printed_output_goes_into_the_answer_not_the_protocol(monkeypatch,
                                                              capsys):
    """Что печатают сценарии, клиент видит в ответе, а в поток протокола — нет."""
    def noisy(**_kwargs):
        print("строка из старого кода")
        return "главный ответ"

    spec = mcp_server.ToolSpec("шумный", "для теста", mcp_server._schema(), noisy)
    server = mcp_server.McpServer(tools=[spec])
    answer = call_tool(server, "шумный")
    text = answer["result"]["content"][0]["text"]
    assert "главный ответ" in text
    assert "строка из старого кода" in text
    # и это же ушло в stderr (в лог клиента), а не в протокол
    assert "строка из старого кода" in capsys.readouterr().err


def test_tool_exception_becomes_a_clear_error_not_a_crash():
    def boom(**_kwargs):
        raise RuntimeError("внутренняя поломка")

    spec = mcp_server.ToolSpec("ломается", "для теста", mcp_server._schema(), boom)
    server = mcp_server.McpServer(tools=[spec])
    answer = call_tool(server, "ломается")
    assert answer["result"]["isError"] is True
    assert "внутренняя поломка" in answer["result"]["content"][0]["text"]


def test_missing_required_argument_is_explained():
    server = mcp_server.McpServer()
    answer = call_tool(server, "powermill_cutting")          # без request
    assert answer["result"]["isError"] is True
    assert "request" in answer["result"]["content"][0]["text"]


def test_long_answer_is_trimmed():
    def long_answer(**_kwargs):
        return "я" * (mcp_server.MAX_TOOL_OUTPUT + 500)

    spec = mcp_server.ToolSpec("длинный", "для теста", mcp_server._schema(), long_answer)
    server = mcp_server.McpServer(tools=[spec])
    text = call_tool(server, "длинный")["result"]["content"][0]["text"]
    assert len(text) < mcp_server.MAX_TOOL_OUTPUT + 300
    assert "обрезано" in text


def test_plan_tool_shows_numbers_and_says_nothing_was_changed():
    server = mcp_server.McpServer()
    answer = call_tool(server, "powermill_plan_operation", material="Сталь 40Х",
                       tool_diameter=16)
    text = answer["result"]["content"][0]["text"]
    assert "ничего ещё не сделано" in text
    assert "S=" in text and "ae=" in text
    assert "копию проекта" in text.lower()


def test_read_report_does_not_walk_outside_the_data_folder(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    (tmp_path / "doctor_report.txt").write_text("всё хорошо", encoding="utf-8")
    server = mcp_server.McpServer()
    # попытка выйти за папку данных не сработает: берём только имя файла
    text = call_tool(server, "powermill_read_report",
                     name="../../../etc/passwd")["result"]["content"][0]["text"]
    assert "passwd" not in text or "нет в" in text
    good = call_tool(server, "powermill_read_report",
                     name="doctor_report.txt")["result"]["content"][0]["text"]
    assert "всё хорошо" in good


# --------------------------------------------------------------------------
# Безопасность: макрос выполняется только по подтверждению и только наш
# --------------------------------------------------------------------------
def test_run_macro_without_confirm_is_refused():
    server = mcp_server.McpServer()
    text = call_tool(server, "powermill_run_macro",
                     name="PM_AI_TEST")["result"]["content"][0]["text"]
    assert "confirm=true" in text
    assert "Не выполнил" in text


def test_run_macro_refuses_someone_elses_macro(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "allowed_macros",
                        lambda: [tmp_path / "PM_AI_TEST.mac"])
    server = mcp_server.McpServer()
    text = call_tool(server, "powermill_run_macro", name="../../evil",
                     confirm=True)["result"]["content"][0]["text"]
    assert "Не нашёл макрос" in text


def test_run_macro_says_how_to_create_macros_when_there_are_none(monkeypatch):
    monkeypatch.setattr(mcp_server, "allowed_macros", list)
    server = mcp_server.McpServer()
    text = call_tool(server, "powermill_run_macro", name="test",
                     confirm=True)["result"]["content"][0]["text"]
    assert "пункт 28" in text


def test_run_macro_asks_powermill_and_reports_answer(monkeypatch):
    """С подтверждением и живым PowerMill макрос действительно отправляется."""
    from src import pm_com

    macro = Path("/tmp/PM_AI_TEST.mac")

    class Session:
        def execute(self, command):
            self.command = command
            return True, "DoCommand('MACRO ...') -> OK"

    session = Session()
    monkeypatch.setattr(mcp_server, "allowed_macros", lambda: [macro])
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", Path("/tmp"))
    monkeypatch.setattr(pm_com, "connect", lambda: (session, "ок"))
    server = mcp_server.McpServer()
    text = call_tool(server, "powermill_run_macro", name="PM_AI_TEST",
                     confirm=True)["result"]["content"][0]["text"]
    assert "Выполнил внутри PowerMill" in text
    assert "PM_AI_TEST.mac" in session.command


def test_run_macro_without_powermill_explains_what_to_do(monkeypatch, tmp_path):
    from src import pm_com

    monkeypatch.setattr(mcp_server, "allowed_macros",
                        lambda: [tmp_path / "PM_AI_TEST.mac"])
    monkeypatch.setattr(pm_com, "connect", lambda: (None, "PowerMill не запущен"))
    server = mcp_server.McpServer()
    text = call_tool(server, "powermill_run_macro", name="PM_AI_TEST",
                     confirm=True)["result"]["content"][0]["text"]
    assert "не отвечает" in text
    assert "пункт 41" in text


def test_only_one_tool_modifies_the_project():
    tools = mcp_server.build_tools()
    changing = [item.name for item in tools if item.modifies_project]
    assert changing == ["powermill_run_macro"]


# --------------------------------------------------------------------------
# Ресурсы: отчёты
# --------------------------------------------------------------------------
def test_resources_list_contains_status_and_existing_reports(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    (tmp_path / "doctor_report.txt").write_text("ок", encoding="utf-8")
    server = mcp_server.McpServer()
    items = call(server, {"jsonrpc": "2.0", "id": 1,
                          "method": "resources/list"})["result"]["resources"]
    uris = [item["uri"] for item in items]
    assert "powermill://status" in uris
    assert "powermill://report/doctor_report.txt" in uris
    # чего нет на диске — того и в списке нет
    assert "powermill://report/plugin_report.txt" not in uris


def test_resource_read_returns_report_text(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    (tmp_path / "pm_link_report.txt").write_text("связь есть", encoding="utf-8")
    server = mcp_server.McpServer()
    answer = call(server, {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                           "params": {"uri": "powermill://report/pm_link_report.txt"}})
    assert "связь есть" in answer["result"]["contents"][0]["text"]


def test_resource_read_of_unknown_uri_is_an_error():
    server = mcp_server.McpServer()
    answer = call(server, {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                           "params": {"uri": "powermill://нет/такого"}})
    assert answer["error"]["code"] == mcp_server.ERROR_PARAMS


def test_status_resource_works_without_powermill(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(mcp_server, "tool_status", lambda: "PowerMill: не запущен")
    server = mcp_server.McpServer()
    answer = call(server, {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                           "params": {"uri": "powermill://status"}})
    assert "не запущен" in answer["result"]["contents"][0]["text"]


# --------------------------------------------------------------------------
# Самопроверка и живой запуск через стандартный ввод-вывод
# --------------------------------------------------------------------------
def test_selftest_passes():
    lines: list[str] = []
    assert mcp_server.selftest(log=lines.append) == 0
    text = "\n".join(lines)
    assert "ВСЁ В ПОРЯДКЕ" in text
    assert "confirm=true" in text                          # защита проверена


def test_selftest_notices_a_broken_tool(monkeypatch):
    bad = mcp_server.ToolSpec("плохой", "для теста", mcp_server._schema(),
                              lambda **_kwargs: (_ for _ in ()).throw(
                                  RuntimeError("нет")))
    monkeypatch.setattr(mcp_server, "build_tools", lambda: [bad])
    assert mcp_server.selftest(log=lambda _line: None) == 2


def test_stdio_conversation_keeps_stdout_clean():
    """Живой запуск: в stdout — только JSON, иначе клиент не поймёт сервер."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    process = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "mcp_server.py")],
        input="\n".join(json.dumps(item) for item in messages) + "\n",
        capture_output=True, text=True, encoding="utf-8", timeout=300,
        cwd=str(PROJECT_ROOT))
    assert process.returncode == 0
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    assert len(lines) == 2                                  # уведомление без ответа
    for line in lines:
        json.loads(line)                                    # падает, если не JSON
    assert "сервер запущен" in process.stderr


# --------------------------------------------------------------------------
# Настройки ИИ-клиента: не перезаписываем молча
# --------------------------------------------------------------------------
def test_server_entry_uses_project_python_and_script():
    from scripts import mcp_setup

    entry = mcp_setup.server_entry()
    assert entry["args"][0].endswith("mcp_server.py")
    assert Path(entry["args"][0]).exists()
    assert entry["cwd"] == str(mcp_setup.PROJECT_ROOT)


def test_vscode_entry_has_stdio_type():
    from scripts import mcp_setup

    vscode = mcp_setup.find_client("vscode")
    assert vscode is not None
    entry = mcp_setup.server_entry(vscode)
    assert entry["type"] == "stdio"
    assert vscode.top_key == "servers"


def test_write_config_keeps_other_servers_and_makes_a_backup(tmp_path):
    from scripts import mcp_setup

    target = tmp_path / "claude_desktop_config.json"
    target.write_text(json.dumps({"mcpServers": {"чужой": {"command": "xyz"}},
                                  "другаяНастройка": 1}), encoding="utf-8")
    client = mcp_setup.Client("claude", "Claude Desktop", target, "mcpServers")
    lines = mcp_setup.write_config(client)
    assert any(line.startswith("✔") for line in lines)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "чужой" in data["mcpServers"]                    # чужое цело
    assert mcp_setup.SERVER_NAME in data["mcpServers"]
    assert data["другаяНастройка"] == 1
    assert target.with_suffix(".json.bak").exists()


def test_write_config_creates_folders_for_a_new_file(tmp_path):
    from scripts import mcp_setup

    target = tmp_path / "нет" / "такой" / "папки" / "mcp.json"
    client = mcp_setup.Client("cursor", "Cursor", target, "mcpServers")
    assert any(line.startswith("✔") for line in mcp_setup.write_config(client))
    assert mcp_setup.SERVER_NAME in json.loads(
        target.read_text(encoding="utf-8"))["mcpServers"]


def test_write_config_refuses_broken_json(tmp_path):
    from scripts import mcp_setup

    target = tmp_path / "mcp.json"
    target.write_text("{это не json", encoding="utf-8")
    client = mcp_setup.Client("cursor", "Cursor", target, "mcpServers")
    lines = mcp_setup.write_config(client)
    assert any(line.startswith("✘") for line in lines)
    assert target.read_text(encoding="utf-8") == "{это не json"   # не тронули


def test_configured_clients_finds_our_server(tmp_path, monkeypatch):
    from scripts import mcp_setup

    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {mcp_setup.SERVER_NAME: {}}}),
                      encoding="utf-8")
    monkeypatch.setattr(mcp_setup, "clients",
                        lambda: [mcp_setup.Client("test", "Тестовый клиент",
                                                  target, "mcpServers")])
    found = mcp_setup.configured_clients()
    assert [client.title for client in found] == ["Тестовый клиент"]


def test_remove_config_takes_only_our_server(tmp_path):
    from scripts import mcp_setup

    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {
        mcp_setup.SERVER_NAME: {}, "чужой": {}}}), encoding="utf-8")
    client = mcp_setup.Client("cursor", "Cursor", target, "mcpServers")
    mcp_setup.remove_config(client)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert mcp_setup.SERVER_NAME not in data["mcpServers"]
    assert "чужой" in data["mcpServers"]


def test_setup_show_prints_ready_block(monkeypatch, tmp_path, capfd):
    """Блок настроек печатается на экран и попадает в отчёт (capfd: свой stdout)."""
    from scripts import mcp_setup

    monkeypatch.setattr(mcp_setup, "REPORT_FILE", tmp_path / "mcp_report.txt")
    assert mcp_setup.main(["--show"]) == 0
    text = capfd.readouterr().out
    assert "mcpServers" in text
    assert "mcp_server.py" in text
    report = (tmp_path / "mcp_report.txt").read_text(encoding="utf-8")
    assert "mcp_server.py" in report


def test_setup_write_all_writes_every_client(monkeypatch, tmp_path):
    from scripts import mcp_setup

    made = [mcp_setup.Client(key, key, tmp_path / f"{key}.json", "mcpServers")
            for key in ("a", "b")]
    monkeypatch.setattr(mcp_setup, "clients", lambda: made)
    monkeypatch.setattr(mcp_setup, "REPORT_FILE", tmp_path / "mcp_report.txt")
    assert mcp_setup.main(["--write", "all"]) == 0
    for client in made:
        data = json.loads(client.path.read_text(encoding="utf-8"))
        assert mcp_setup.SERVER_NAME in data["mcpServers"]


def test_setup_unknown_client_is_an_error(monkeypatch, tmp_path):
    from scripts import mcp_setup

    monkeypatch.setattr(mcp_setup, "REPORT_FILE", tmp_path / "mcp_report.txt")
    assert mcp_setup.main(["--write", "нет_такого_клиента"]) == 2


def test_report_lists_where_the_server_is_registered(monkeypatch, tmp_path):
    from scripts import mcp_setup

    target = tmp_path / "mcp.json"
    client = mcp_setup.Client("cursor", "Cursor", target, "mcpServers")
    monkeypatch.setattr(mcp_setup, "clients", lambda: [client])
    lines = mcp_setup.report_lines(["✔ Cursor: прописал"])
    text = "\n".join(lines)
    assert "ПОДКЛЮЧЕНИЕ К ИИ-КЛИЕНТУ" in text
    assert "Как проверить в клиенте" in text
    assert "mcpServers" in text                             # блок для ручной вставки
    assert "powermill_cutting" in text                      # на что смотреть


# --------------------------------------------------------------------------
# Кнопка в окне, лента, панель, проверка компьютера и батники
# --------------------------------------------------------------------------
def test_button_list_has_mcp_in_setup_group():
    from src import pm_buttons

    action = pm_buttons.by_key("mcp")
    assert action is not None
    assert action.group == pm_buttons.GROUP_SETUP
    assert action.target.replace("\\", "/") == "scripts/mcp_setup.bat"
    assert pm_buttons.validate() == []


def test_window_and_panel_see_the_new_button():
    from src import app_window, pm_buttons

    titles = [plan.title for plan in app_window.plans()]
    assert "Подключить ИИ-клиент (MCP)" in titles
    assert any(action.key == "mcp" for action in pm_buttons.pane_actions())


def test_doctor_reports_mcp_state(monkeypatch, tmp_path):
    """Проверка компьютера видит MCP: прописан ли сервер хоть в одном клиенте."""
    from scripts import mcp_setup
    from src import doctor

    client = mcp_setup.Client("c", "Тестовый клиент", tmp_path / "x.json",
                              "mcpServers")
    monkeypatch.setattr(mcp_setup, "clients", lambda: [client])
    assert "44" in doctor.check_mcp(PROJECT_ROOT).title

    # нет клиента с нашим сервером -> подсказка, куда идти
    check = doctor.check_mcp(PROJECT_ROOT)
    assert check.status == doctor.STATUS_WARN
    assert "пункт 44" in check.advice

    # прописали -> проверка довольна
    client.path.write_text(json.dumps({"mcpServers": {mcp_setup.SERVER_NAME: {}}}),
                           encoding="utf-8")
    check = doctor.check_mcp(PROJECT_ROOT)
    assert check.status == doctor.STATUS_OK
    assert "Тестовый клиент" in check.detail


def test_bats_for_mcp_are_double_clickable():
    for name in ("scripts/mcp_setup.bat", "scripts/mcp_server.bat"):
        path = PROJECT_ROOT / name
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "chcp 65001" in text, name
        assert ".venv\\Scripts\\python.exe" in text, name
        assert "venv\\Scripts\\python.exe" in text, name
        assert "pause" in text, name
        assert path.read_bytes().count(b"\r\n") > 5, name

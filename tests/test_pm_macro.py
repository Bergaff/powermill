"""Тесты макросов «PowerMill AI» внутри PowerMill (шаг 2.2 без плагина).

Ключевая проверка: сгенерированные макросы должны состоять ТОЛЬКО из команд,
подтверждённых документацией Autodesk. Их проверяет наш же словарь PML
(src/pml_vocab.py) — если я выдумаю команду, тест это поймает.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import pm_bridge, pm_macro, pml_vocab


@pytest.fixture
def macro_env(tmp_path, monkeypatch):
    """Перенаправляем файлы моста в tmp, чтобы не трогать рабочие."""
    monkeypatch.setattr(pm_macro, "MACRO_DIR", tmp_path / "macros")
    monkeypatch.setattr(pm_macro, "REQUEST_FILE", tmp_path / "pm_request.txt")
    monkeypatch.setattr(pm_macro, "ANSWER_FILE", tmp_path / "pm_answer.txt")
    monkeypatch.setattr(pm_macro, "PROJECT_FILE", tmp_path / "pm_project.txt")
    monkeypatch.setattr(pm_bridge, "REQUEST_FILE", tmp_path / "pm_request.txt")
    monkeypatch.setattr(pm_bridge, "ANSWER_FILE", tmp_path / "pm_answer.txt")
    return tmp_path


VOCAB = {"entities": ["model", "boundary", "tool", "toolpath", "workplane",
                      "ncprogram", "stockmodel", "pattern"], "parameters": []}


# --------------------------------------------------------------------------
# Макросы состоят из проверенных команд
# --------------------------------------------------------------------------
def test_ask_macro_passes_own_validator():
    report = pml_vocab.validate(pm_macro.ask_macro(), VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_snapshot_macro_passes_own_validator():
    report = pml_vocab.validate(pm_macro.snapshot_macro(), VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_ask_macro_has_menu_and_input():
    code = pm_macro.ask_macro()
    assert "INPUT CHOICE" in code
    assert "INPUT " in code
    assert "MESSAGE INFO" in code
    assert "MACRO PAUSE" in code


def test_ask_macro_writes_request_and_runs_launcher():
    code = pm_macro.ask_macro()
    assert "FILE OPEN" in code and "FOR WRITE AS" in code
    assert "FILE WRITE" in code and " TO " in code
    assert "FILE CLOSE" in code
    assert "OLE FILEACTION 'OPEN'" in code
    assert "FILE READ" in code and " FROM " in code


def test_ask_macro_menu_matches_modes():
    code = pm_macro.ask_macro()
    for _number, title in [(i, t) for i, (_c, t) in enumerate(pm_macro.MODES)]:
        assert title in code


def test_snapshot_macro_collects_all_sections():
    code = pm_macro.snapshot_macro()
    for folder in ("Model", "Boundary", "Tool", "Toolpath", "Workplane",
                   "NCProgram", "StockModel", "Pattern"):
        assert f'FOLDER("{folder}")' in code


def test_macros_have_no_unproven_commands():
    """Страховка: макросы не должны содержать команд-самозванцев."""
    for code in (pm_macro.ask_macro(), pm_macro.snapshot_macro()):
        lowered = code.lower()
        for fake in ("create boundary", "add default allowance", "check toolpath",
                     "runmacro", "executemacro"):
            assert fake not in lowered


def test_test_macro_checks_launch_by_comparing_content():
    """Запуск программы проверяется сравнением содержимого файла, а не EXISTS()."""
    code = pm_macro.test_macro()
    assert "FILE WRITE \"WAIT\" TO out" in code
    assert "IF $after_text == $text" in code
    assert "EXISTS(FILEOPEN" not in code          # такой функции в PML нет
    assert "OLE FILEACTION 'OPEN' $launcher" in code


def test_test_macro_passes_own_validator():
    report = pml_vocab.validate(pm_macro.test_macro(), VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_ask_macro_converts_mode_number_to_string():
    """INPUT CHOICE возвращает номер, а в файл нужно писать текст."""
    assert "STRING($mode)" in pm_macro.ask_macro()


def test_launchers_include_test_bat(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", tmp_path)
    launchers = pm_macro.launchers()
    assert "pm_test.bat" in launchers
    assert "POWERMILL-AI-OK" in launchers["pm_test.bat"]


def test_file_open_paths_use_forward_slashes(monkeypatch):
    """В FILE OPEN путь идёт с ПРЯМЫМИ слэшами — как у самой PowerMill.

    Почему: на живом PowerMill 2026 макрос с путём `E:\\powermill-ai\\...`
    вместо открытия файла показал приглашение «Выберите файл >». PowerMill сам
    отдаёт пути через `/` (`project_pathname(0)`), и рабочие макросы с форума
    открывают файлы так же: `FILE OPEN "S:/Templates/tool.pmlent" FOR WRITE AS output`.
    Windows понимает оба разделителя, поэтому в макросе — `/`.
    """
    win = r"E:\powermill-ai\output"
    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", Path(win))
    monkeypatch.setattr(pm_macro, "REQUEST_FILE", Path(win + r"\pm_request.txt"))
    monkeypatch.setattr(pm_macro, "ANSWER_FILE", Path(win + r"\pm_answer.txt"))
    monkeypatch.setattr(pm_macro, "PROJECT_FILE", Path(win + r"\pm_project.txt"))
    monkeypatch.setattr(pm_macro, "TEST_FILE", Path(win + r"\pm_test.txt"))

    for code in (pm_macro.ask_macro(), pm_macro.snapshot_macro(),
                 pm_macro.test_macro()):
        assert chr(92) * 2 not in code, "в макросе удвоенные обратные слэши"
        assert "E:/powermill-ai/output" in code
        for line in code.splitlines():
            if "FILE OPEN" in line:
                assert chr(92) not in line, f"обратный слэш в FILE OPEN: {line}"


def test_macros_reset_localvars_first():
    """Без RESET LOCALVARS второй запуск макроса падает.

    На форуме Autodesk: «local variable is already define» при повторном
    запуске макроса; в рабочих макросах первой строкой стоит `reset localvars`.
    """
    for code in (pm_macro.ask_macro(), pm_macro.snapshot_macro(),
                 pm_macro.test_macro()):
        head = code.splitlines()[:15]
        assert "RESET LOCALVARS" in head, code.splitlines()[:3]


def test_print_and_message_get_one_value():
    """В PRINT/MESSAGE передаём одно значение: склейка — только в $переменных.

    Так пишут в рабочих макросах с форума Autodesk: сначала
    `$Ligne = $tp.name + ";" + $tp.Number`, потом `FILE WRITE $Ligne TO out`.
    Что команда принимает выражение с `+`, мы на живом PowerMill не проверяли —
    поэтому не рискуем: собираем текст в переменную и печатаем её.
    """
    from src import power_mill_link

    texts = (pm_macro.ask_macro(), pm_macro.snapshot_macro(), pm_macro.test_macro(),
             power_mill_link.probe_macro("E:/powermill-ai/output/pm_project.txt"))
    for code in texts:
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith(("PRINT", "MESSAGE")):
                assert " + " not in stripped, stripped


def test_snapshot_macro_checks_written_file():
    """Снимок читается обратно — иначе не видно, записался файл или нет."""
    code = pm_macro.snapshot_macro()
    assert "FILE OPEN $outfile FOR READ AS chk" in code
    assert "INT $pm_count = SIZE($pm_check_lines)" in code
    assert "IF $pm_count == 0 {" in code


def test_forward_slashes_are_normalized_for_windows_paths():
    """Если путь пришёл как E:/powermill-ai, в макросе он станет E:\\powermill-ai."""
    assert pm_macro._win_path(Path("E:/powermill-ai/output")) == "E:\\powermill-ai\\output"
    assert pm_macro._win_path(Path("/tmp/pmtest/data")) == "/tmp/pmtest/data"
    # для макросов — наоборот, прямые слэши (см. test_file_open_paths_use_forward_slashes)
    assert pm_macro.pml_path(Path("E:\\powermill-ai\\output")) == "E:/powermill-ai/output"
    assert pm_macro.pml_path(Path("/tmp/pmtest/data")) == "/tmp/pmtest/data"


def test_launcher_uses_windows_path_for_data_root(monkeypatch):
    monkeypatch.setattr(pm_macro, "DATA_ROOT", "E:/powermill-ai")
    text = pm_macro.launchers()["pm_test.bat"]
    assert 'cd /d "E:\\powermill-ai"' in text


def test_paths_inside_macros_use_single_quotes():
    """Путь в макросе — в одинарных кавычках, как в примерах Autodesk."""
    assert "STRING $f = '" in pm_macro.test_macro()


# --------------------------------------------------------------------------
# Запись файлов
# --------------------------------------------------------------------------
def test_write_all_creates_macros_and_launchers(macro_env, monkeypatch):
    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", macro_env / "out")
    written = pm_macro.write_all()
    names = {p.name for p in written}
    assert {"PM_AI_ASK.mac", "PM_AI_SNAPSHOT.mac",
            "pm_answer.bat", "pm_snapshot.bat"} <= names
    for path in written:
        if path.suffix == ".mac":
            assert path.read_bytes().count(b"\r\n") > 5


def test_launchers_call_our_scripts(macro_env, monkeypatch):
    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", macro_env / "out")
    launchers = pm_macro.launchers()
    assert "scripts.pm_answer" in launchers["pm_answer.bat"]
    assert "scripts.load_project" in launchers["pm_snapshot.bat"]
    assert "--auto" in launchers["pm_snapshot.bat"]


# --------------------------------------------------------------------------
# Разбор запроса от макроса
# --------------------------------------------------------------------------
def test_parse_request_mode_number():
    request = pm_bridge.parse_request("MODE=2\nToolpath calculation failed")
    assert request["mode"] == "error"
    assert request["query"] == "Toolpath calculation failed"


def test_parse_request_mode_name():
    request = pm_bridge.parse_request("MODE=macro\nсоздать границы")
    assert request["mode"] == "macro"
    assert request["query"] == "создать границы"


def test_parse_request_multiline_query():
    request = pm_bridge.parse_request("MODE=0\nпервая строка\nвторая строка")
    assert request["query"] == "первая строка\nвторая строка"


def test_parse_request_without_mode_defaults_to_ask():
    request = pm_bridge.parse_request("просто вопрос")
    assert request["mode"] == "ask"
    assert request["query"] == "просто вопрос"


def test_parse_request_unknown_mode_number():
    assert pm_bridge.parse_request("MODE=99\nx")["mode"] == "ask"


def test_mode_code_mapping():
    assert pm_bridge.mode_code(0) == "ask"
    assert pm_bridge.mode_code(1) == "macro"
    assert pm_bridge.mode_code(2) == "error"
    assert pm_bridge.mode_code(3) == "cutting"


# --------------------------------------------------------------------------
# Ответ
# --------------------------------------------------------------------------
class FakeAI:
    def ask(self, query):
        return f"ОТВЕТ: {query}"

    def macro(self, query, save=True):
        return f"```pml\n// {query}\nPRINT \"ok\"\n```"

    def error(self, query):
        return f"РАЗБОР: {query}"


def test_handle_ask_mode_writes_answer(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=0\nкак задать припуск\n", encoding="utf-8")
    rc = pm_bridge.handle(ai=FakeAI(), verbose=False)
    assert rc == 0
    text = pm_macro.ANSWER_FILE.read_text(encoding="utf-8")
    assert "ОТВЕТ: как задать припуск" in text
    assert "PowerMill AI · режим: ask" in text


def test_handle_macro_mode_strips_markdown_fences(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=1\nграницы\n", encoding="utf-8")
    pm_bridge.handle(ai=FakeAI(), verbose=False)
    text = pm_macro.ANSWER_FILE.read_text(encoding="utf-8")
    assert "```" not in text
    assert "PRINT \"ok\"" in text


def test_handle_cutting_works_without_ai(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=3\nСталь 40Х, фреза D16, черновая\n",
                                     encoding="utf-8")
    rc = pm_bridge.handle(verbose=False)          # ai=None: ИИ не нужен
    assert rc == 0
    text = pm_macro.ANSWER_FILE.read_text(encoding="utf-8")
    assert "S (об/мин)" in text


def test_handle_empty_request(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=0\n(пустой запрос)\n", encoding="utf-8")
    rc = pm_bridge.handle(ai=FakeAI(), verbose=False)
    assert rc == 3
    assert "Пустой запрос" in pm_macro.ANSWER_FILE.read_text(encoding="utf-8")


def test_handle_missing_request(macro_env):
    rc = pm_bridge.handle(path=macro_env / "нет.txt", verbose=False)
    assert rc == 2


def test_placeholder_is_written_before_work(macro_env):
    path = pm_bridge.write_placeholder()
    text = Path(path).read_text(encoding="utf-8")
    assert "готовит ответ" in text


def test_answer_truncated_for_power_mill():
    long_text = "строка\n" * 3000
    cleaned = pm_bridge.clean_for_power_mill(long_text)
    assert len(cleaned) < 4200
    assert "продолжение" in cleaned


def test_answer_removes_markdown():
    cleaned = pm_bridge.clean_for_power_mill("## Заголовок\n**важно**\n```pml\nPRINT\n```")
    assert "##" not in cleaned
    assert "**" not in cleaned
    assert "```" not in cleaned

"""Тесты макросов «PowerMill AI» внутри PowerMill (шаг 2.2 без плагина).

Ключевая проверка: сгенерированные макросы должны состоять ТОЛЬКО из команд,
подтверждённых документацией Autodesk. Их проверяет наш же словарь PML
(src/pml_vocab.py) — если я выдумаю команду, тест это поймает.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import pml_files, pm_bridge, pm_macro, pml_vocab


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
    assert 'STRING $pm_text = "WAIT"' in code
    assert "FILE WRITE $pm_text TO tfile" in code
    assert "IF $after_text == $text" in code
    assert "EXISTS(FILEOPEN" not in code          # такой функции в PML нет
    assert "OLE FILEACTION 'OPEN' $launcher" in code


def test_test_macro_marks_every_step_with_its_own_file():
    """Каждый шаг оставляет свой файл: по последнему видно, где макрос встал.

    На живом PowerMill макрос остановился на записи в файл, и по логу консоли
    нельзя было понять, на каком именно шаге. Теперь шаг 1..5 отмечается файлами
    pm_trace_1.txt … pm_trace_5.txt (открыть — пункт 29), а в окне печатаются
    строки «powermill ai: шаг N ок».
    """
    code = pm_macro.test_macro()
    for path in pm_macro.trace_files():
        assert pm_macro.pml_path(path) in code, path
    for index in range(1, 6):
        assert f"powermill ai: шаг {index}" in code


def test_test_macro_uses_fresh_file_handles():
    """Дескрипторы файлов не повторяются и без цифр: незакрытый файл прошлого
    запуска не мешает новому, а имена — как в рабочих макросах Autodesk."""
    code = pm_macro.test_macro()
    handles = [line.split()[-1] for line in code.splitlines()
               if line.startswith("FILE OPEN")]
    assert len(handles) == len(set(handles)), handles
    assert "tfile" in handles and "marka" in handles and "marke" in handles
    assert all(handle.isalpha() for handle in handles), handles


def test_macro_text_never_goes_into_file_write_as_literal():
    """Живое правило PowerMill: в FILE WRITE, PRINT и MACRO PAUSE — переменная.

    На живом PowerMill 2026 строка `FILE WRITE "WAIT" TO tf1` дала ошибку
    «недопустимый элемент или команда». Во всех рабочих макросах с форума
    Autodesk в FILE WRITE передаётся переменная, поэтому текст сначала
    присваивается строке. Этот тест не даст вернуть литерал обратно.
    """
    from src import pm_edit, pm_operation, power_mill_link

    texts = (pm_macro.ask_macro(), pm_macro.snapshot_macro(), pm_macro.test_macro(),
             power_mill_link.probe_macro("E:/powermill-ai/output/pm_project.txt"),
             pm_operation.build_macro(pm_operation.OperationPlan(
                 toolpath_name="Черновая", tool_name="D16", tool_diameter=16)),
             pm_edit.edit_macro([pm_edit.SpeedFeed(toolpath="Черновая", spindle=4500,
                                                   feed=1200, plunge=400)]))
    checked = 0
    for code in texts:
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith(("//", ";")):
                continue
            for command in ("FILE WRITE", "PRINT", "MACRO PAUSE"):
                if stripped.startswith(command):
                    argument = stripped[len(command):].strip()
                    assert argument.startswith("$"), f"литерал в {command}: {stripped}"
                    checked += 1
            if stripped.startswith("MESSAGE"):
                # MESSAGE INFO/WARN/ERROR — текст тоже должен быть переменной
                last = stripped.split()[-1]
                assert last.startswith("$"), f"литерал в MESSAGE: {stripped}"
                checked += 1
    assert checked > 40, f"подозрительно мало проверенных строк: {checked}"


def test_ask_macro_asks_material_and_tool_for_cutting_mode():
    """Для режимов резания макрос сам спрашивает материал и фрезу.

    Иначе на вопрос «какой фрезой сделать» ассистент отвечает по «стали
    среднеуглеродистой» и диаметру по умолчанию, и в ответе появляется
    «материал не распознан» (так и было на живом PowerMill 24.09).
    """
    code = pm_macro.ask_macro()
    assert "IF $mode == 3 {" in code                       # 3 — «Режимы резания»
    assert 'INPUT "Материал (например: сталь 40Х, 12Х18Н10Т, Д16Т):"' in code
    assert 'INPUT "Фреза: диаметр и число зубьев (например: D12 z4):"' in code
    assert '$question = $question + "; материал " + $pm_material' in code
    assert '$question = $question + "; фреза " + $pm_tool' in code
    # и такие уточнения ассистент действительно понимает
    from src import cutting

    answer, _data = cutting.answer("какой фрезой сделать; материал сталь 40Х; фреза D16 z4")
    assert "Сталь 40Х" in answer.splitlines()[0]
    assert "D16 z4" in answer.splitlines()[0]


def test_ask_macro_cutting_index_matches_modes():
    """Номер режима в макросе и в списке MODES — одно и то же место (3)."""
    index = [code for code, _title in pm_macro.MODES].index("cutting")
    assert index == 3
    assert "IF $mode == 3 {" in pm_macro.ask_macro()


def test_ask_macro_message_uses_variable():
    """В MESSAGE тоже передаём переменную — как в FILE WRITE и PRINT."""
    code = pm_macro.ask_macro()
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("MESSAGE"):
            assert stripped.split()[-1].startswith("$"), stripped


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


def test_print_message_and_file_write_get_one_value():
    """В PRINT/MESSAGE/FILE WRITE передаём одно значение: склейка — в $переменных.

    Так пишут в рабочих макросах с форума Autodesk: сначала
    `$Ligne = $tp.name + ";" + $tp.Number`, потом `FILE WRITE $Ligne TO out`.

    Проверено на живом PowerMill 2026 (лог консоли 24.09): строка
    `FILE WRITE "MODE=" + STRING($mode) TO req` останавливала макрос ровно на
    этом месте. Поэтому выражение живёт только в присваивании, а в FILE WRITE,
    PRINT и MESSAGE уходит готовая переменная.
    """
    from src import pm_edit, pm_operation, power_mill_link

    texts = (pm_macro.ask_macro(), pm_macro.snapshot_macro(), pm_macro.test_macro(),
             power_mill_link.probe_macro("E:/powermill-ai/output/pm_project.txt"),
             pm_operation.build_macro(pm_operation.OperationPlan(
                 toolpath_name="Черновая", tool_name="D16", tool_diameter=16)),
             pm_edit.edit_macro([pm_edit.SpeedFeed(toolpath="Черновая", spindle=4500,
                                                   feed=1200, plunge=400)]))
    checked = 0
    for code in texts:
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith(("//", ";")):
                continue
            if stripped.startswith(("PRINT", "MESSAGE", "FILE WRITE")):
                assert " + " not in stripped, stripped
                checked += 1
    assert checked > 30, f"подозрительно мало проверенных строк: {checked}"


def test_ask_macro_writes_mode_line_from_a_variable():
    """Номер режима склеивается со строкой в присваивании, а не в FILE WRITE."""
    code = pm_macro.ask_macro()
    assert 'STRING $mode_line = "MODE=" + STRING($mode)' in code
    assert "FILE WRITE $mode_line TO askq" in code
    # именно в команде FILE WRITE склейки быть не должно (в комментарии можно)
    for line in code.splitlines():
        if line.strip().startswith("FILE WRITE"):
            assert " + " not in line, line


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
    text = pml_files.read(pm_macro.ANSWER_FILE)
    assert "ОТВЕТ: как задать припуск" in text
    assert "PowerMill AI · режим: ask" in text


def test_handle_macro_mode_strips_markdown_fences(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=1\nграницы\n", encoding="utf-8")
    pm_bridge.handle(ai=FakeAI(), verbose=False)
    text = pml_files.read(pm_macro.ANSWER_FILE)
    assert "```" not in text
    assert "PRINT \"ok\"" in text


def test_handle_cutting_works_without_ai(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=3\nСталь 40Х, фреза D16, черновая\n",
                                     encoding="utf-8")
    rc = pm_bridge.handle(verbose=False)          # ai=None: ИИ не нужен
    assert rc == 0
    text = pml_files.read(pm_macro.ANSWER_FILE)
    assert "S (об/мин)" in text


def test_handle_empty_request(macro_env):
    pm_macro.REQUEST_FILE.write_text("MODE=0\n(пустой запрос)\n", encoding="utf-8")
    rc = pm_bridge.handle(ai=FakeAI(), verbose=False)
    assert rc == 3
    assert "Пустой запрос" in pml_files.read(pm_macro.ANSWER_FILE)


def test_handle_missing_request(macro_env):
    rc = pm_bridge.handle(path=macro_env / "нет.txt", verbose=False)
    assert rc == 2


def test_placeholder_is_written_before_work(macro_env):
    path = pm_bridge.write_placeholder()
    text = pml_files.read(path)
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

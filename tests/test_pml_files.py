"""
Тесты файлов обмена с PowerMill (CP1251 + автоопределение при чтении).

Повод: на живом PowerMill 2026 макрос в UTF-8 показывал русский текст как
«РџРѕРІРµСЂРєР°» — PowerMill читает `.mac` в системной кодировке. Поэтому
макросы и файлы ответов пишем в CP1251, а читаем с автоопределением
(остались файлы от прошлых версий, их писал Python в UTF-8).
"""
from __future__ import annotations

from pathlib import Path

from src import pml_files


def test_encode_uses_cp1251():
    data = pml_files.encode("Проверка моста")
    assert data.decode("cp1251") == "Проверка моста"
    # и это действительно НЕ utf-8 (иначе PowerMill покажет кракозябры)
    assert data != "Проверка моста".encode("utf-8")


def test_ascii_commands_stay_byte_identical():
    """Команды и пути — ASCII, они не должны меняться от кодировки."""
    text = "FILE OPEN $f FOR WRITE AS out\nSTRING $f = 'E:/powermill-ai/output'"
    assert pml_files.encode(text) == text.encode("ascii")


def test_sanitize_replaces_unsupported_symbols():
    assert pml_files.sanitize("готово → смотри") == "готово -> смотри"
    assert pml_files.sanitize("⚙️ Режимы 📚 Справка") == " Режимы  Справка"
    assert pml_files.sanitize("✔ ок ✘ нет") == "+ ок - нет"
    # русские буквы, «ёлочки» и тире в CP1251 есть — их не трогаем
    for char in ("Ё", "ё", "«", "»", "—", "…"):
        assert char in pml_files.sanitize(f"текст {char} текст")


def test_write_adds_crlf_and_cp1251(tmp_path):
    path = pml_files.write(tmp_path / "PM_TEST.mac", "STRING $a = \"привет\"\nPRINT $a\n")
    data = path.read_bytes()
    assert data.count(b"\r\n") == 2
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert "привет" in data.decode("cp1251")


def test_write_creates_folders(tmp_path):
    path = pml_files.write(tmp_path / "нет" / "такой" / "папки.mac", "PRINT $a\n")
    assert path.exists()


def test_read_autodetects_utf8_and_cp1251(tmp_path):
    utf8_file = tmp_path / "utf8.txt"
    utf8_file.write_bytes("МОДЕЛИ: Деталь1".encode("utf-8"))
    assert pml_files.read(utf8_file) == "МОДЕЛИ: Деталь1"

    cp_file = tmp_path / "cp1251.txt"
    cp_file.write_bytes("МОДЕЛИ: Деталь1".encode("cp1251"))
    assert pml_files.read(cp_file) == "МОДЕЛИ: Деталь1"


def test_read_survives_broken_bytes(tmp_path):
    broken = tmp_path / "broken.txt"
    broken.write_bytes(b"\xff\xfe\x00 MODELS: part")
    text = pml_files.read(broken)
    assert "MODELS" in text          # мусор не должен ломать чтение


def test_decode_round_trip():
    for text in ("STEP;tool_create;ok;создана фреза", "MODELS:", "готово"):
        assert pml_files.decode(pml_files.encode(text)) == text


def test_answer_file_for_power_mill_is_cp1251(tmp_path, monkeypatch):
    """Ответ для окна PowerMill пишется в CP1251, иначе там будут кракозябры."""
    from src import pm_bridge

    target = tmp_path / "pm_answer.txt"
    pm_bridge.write_answer("Ответ: S=4500, F=1200 ⚙️", path=target)
    raw = target.read_bytes()
    assert "Ответ: S=4500, F=1200".encode("cp1251") in raw
    assert raw.decode("cp1251").count("?") <= 1        # только за эмодзи
    assert "Ответ: S=4500" in pml_files.read(target)


def test_request_file_written_in_cp1251_is_read_back(tmp_path, monkeypatch):
    """Запрос, который макрос пишет в CP1251, ассистент читает правильно."""
    from src import pm_bridge, pm_macro

    request = tmp_path / "pm_request.txt"
    request.write_bytes("MODE=3\nсталь 40Х фреза D16".encode("cp1251"))
    monkeypatch.setattr(pm_macro, "REQUEST_FILE", request)
    monkeypatch.setattr(pm_macro, "ANSWER_FILE", tmp_path / "pm_answer.txt")
    monkeypatch.setattr(pm_bridge, "REQUEST_FILE", request)
    monkeypatch.setattr(pm_bridge, "ANSWER_FILE", tmp_path / "pm_answer.txt")

    rc = pm_bridge.handle(path=request, ai=None)
    assert rc == 0
    answer = pml_files.read(tmp_path / "pm_answer.txt")
    assert "S" in answer and "F" in answer             # расчёт режимов прошёл


def test_macros_written_to_disk_are_cp1251(tmp_path, monkeypatch):
    from src import pm_macro

    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pm_macro, "MACRO_DIR", tmp_path / "pm_macros")
    written = pm_macro.write_all()
    macros = [p for p in written if p.suffix == ".mac"]
    assert macros
    for path in macros:
        raw = path.read_bytes()
        assert b"\r\n" in raw
        raw.decode("cp1251")                            # читается как CP1251
        assert "PowerMill AI" in raw.decode("cp1251")   # русский текст на месте
        assert raw != raw.decode("cp1251").encode("utf-8")


def test_no_utf8_mojibake_in_written_macros(tmp_path, monkeypatch):
    """Страховка от возврата UTF-8: в файле нет последовательностей UTF-8."""
    from src import pm_macro

    monkeypatch.setattr(pm_macro, "MACRO_DIR", tmp_path / "pm_macros")
    for path in pm_macro.write_all():
        if path.suffix != ".mac":
            continue
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            continue                                    # UTF-8 не проходит — это ожидаемо
        # если файл всё же валиден как UTF-8, в нём не должно быть русского
        assert not any("А" <= char <= "я" for char in raw.decode("utf-8"))


def test_sanitize_keeps_file_paths_intact():
    text = "STRING $f = 'E:/powermill-ai/output/pm_test.txt'"
    assert pml_files.sanitize(text) == text
    assert Path("E:/powermill-ai/output/pm_test.txt").name == "pm_test.txt"


# --------------------------------------------------------------------------
# Имена файловых дескрипторов: «handle уже используется»
# --------------------------------------------------------------------------
def test_handle_is_unique_and_alphanumeric():
    names = [pml_files.file_handle() for _ in range(50)]
    assert len(set(names)) == 50
    assert all(name.isalnum() and name[:1].isalpha() for name in names)


def test_handles_survive_power_mill_naming():
    """Имя должно быть одним словом: PML не понимает «out.1» или «out-1»."""
    for _ in range(10):
        name = pml_files.file_handle("p")
        assert name.isascii() and name.isalnum()


def test_unique_handles_rewrites_macro_but_not_text():
    text = ("FILE OPEN $f FOR WRITE AS out\n"
            "FILE WRITE $x TO out\n"
            "FILE CLOSE out\n"
            "PRINT \"out of range\"\n")          # это не дескриптор, трогать нельзя
    fixed = pml_files.unique_handles(text)
    handle = fixed.split("AS ")[1].split("\n")[0]
    assert handle != "out"                       # имя стало уникальным
    assert f"FILE WRITE $x TO {handle}" in fixed
    assert f"FILE CLOSE {handle}" in fixed
    assert "out of range" in fixed               # текст в кавычках не пострадал
    assert " of range" in fixed                  # и внутрь строки не залезли


def test_unique_handles_keeps_open_close_pairs_together():
    text = ("FILE OPEN $a FOR WRITE AS chk_a1\nFILE CLOSE chk_a1\n"
            "FILE OPEN $b FOR WRITE AS chk_a2\nFILE CLOSE chk_a2\n")
    fixed = pml_files.unique_handles(text)
    names = [part.split("AS ")[1].split("\n")[0] for part in fixed.split("FILE OPEN")[1:]]
    assert len(set(names)) == 2
    for name in names:
        assert fixed.count(name) == 2


def test_unique_handles_changes_every_call():
    first = pml_files.unique_handles("FILE CLOSE out")
    second = pml_files.unique_handles("FILE CLOSE out")
    assert first != second


def test_release_handles_asks_power_mill_and_ignores_answers():
    calls: list[str] = []

    class Session:
        def execute(self, command):
            calls.append(command)
            return (True, "ошибка")       # файл не был открыт — ответ не важен

    attempted = pml_files.release_handles(Session())
    closes = [command for command in calls if command.startswith("FILE CLOSE ")]
    assert "FILE CLOSE out" in closes and "FILE CLOSE chkout" in closes
    assert attempted == [command.split()[-1] for command in closes]


def test_release_handles_silences_power_mill_dialogs():
    """Иначе на «FILE CLOSE chkout» человеку выскакивало «неизвестный handle».

    Имя может быть не открыто — и это нормально: мы угадываем, что осталось
    от оборванного макроса. Окна на время уборки выключаются и возвращаются
    обратно (даже если что-то оборвалось).
    """
    calls: list[str] = []

    class Session:
        def execute(self, command):
            calls.append(command)
            return (True, "ок")

    pml_files.release_handles(Session())
    assert calls[0] == "DIALOGS MESSAGE OFF"
    assert calls[1] == "DIALOGS ERROR OFF"
    assert calls[-2:] == ["DIALOGS ERROR ON", "DIALOGS MESSAGE ON"]


def test_release_handles_restores_dialogs_after_a_failure():
    import pytest as _pytest

    calls: list[str] = []

    class Session:
        def execute(self, command):
            calls.append(command)
            if command == "FILE CLOSE chkout":
                raise RuntimeError("PowerMill закрылся")
            return (True, "ок")

    pml_files.release_handles(Session())
    assert calls[-2:] == ["DIALOGS ERROR ON", "DIALOGS MESSAGE ON"]
    assert "FILE CLOSE out" in calls


def test_release_handles_survives_a_broken_bridge():
    class Session:
        def execute(self, command):
            raise RuntimeError("PowerMill закрылся")

    assert pml_files.release_handles(Session()) == []


def test_unique_handles_does_not_touch_paths():
    """Папка с именем out или строка «out of range» — не дескриптор."""
    text = ("STRING $f = 'E:/out/detail.txt'\n"
            "FILE OPEN $f FOR WRITE AS out\n"
            "PRINT \"out of range\"\n")
    fixed = pml_files.unique_handles(text)
    assert "'E:/out/detail.txt'" in fixed
    assert '"out of range"' in fixed
    handle = fixed.split(" AS ")[1].split("\n")[0]
    assert handle != "out" and handle.startswith("out")


# --------------------------------------------------------------------------
# Общая проверка всех наших макросов: файл открыт раньше, чем в него пишут
# --------------------------------------------------------------------------
def _handle_problems(text: str) -> list[str]:
    """Строки, которые обращаются к неоткрытому дескриптору файла."""
    import re

    opened: set[str] = set()
    bad: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        match = re.search(r"FILE OPEN \S+ FOR \w+ AS (\w+)", line)
        if match:
            opened.add(match.group(1))
            continue
        match = re.search(r"FILE (?:WRITE \S+|READ \S+) (?:TO|FROM) (\w+)", line)
        if match and match.group(1) not in opened:
            bad.append(line)
        match = re.search(r"FILE CLOSE (\w+)", line)
        if match and match.group(1) not in opened:
            bad.append(line)
    return bad


def test_all_our_macros_open_files_before_using_them():
    """У каждого дескриптора в макросе есть свой `FILE OPEN`.

    Так ловится рассогласование после переименования дескрипторов: PowerMill на
    неизвестный handle отвечает «неизвестный handle: <имя>» и останавливает
    макрос — а отличить это от ошибки в проекте трудно.
    """
    from src import pm_check, pm_edit, pm_macro, pm_nc, pm_operation

    operation = pm_operation.OperationPlan(
        toolpath_name="Chernovaya_D16", tool_name="D16_Freza", rpm=2980,
        feed=950, plunge=570, calculate=True)
    for plan in (operation, pm_operation.OperationPlan(
            toolpath_name="C", tool_name="D16", create_tool=False)):
        # части проверяем так, как их увидит PowerMill: файлом, вместе с
        # открытием файла отчёта (в тексте самой части этого открытия нет)
        import tempfile

        folder = Path(tempfile.mkdtemp())
        for _part, path in pm_operation.write_parts(plan, folder=folder):
            text = path.read_text(encoding="cp1251")
            assert not _handle_problems(text), path.name
        assert not _handle_problems(pm_operation.build_macro(plan))

    assert not _handle_problems(pm_check.build_macro(
        pm_check.CheckPlan(toolpaths=["Chernovaya_D16", "Vtoraya"])))
    assert not _handle_problems(pm_nc.build_macro(
        pm_nc.NcPlan(toolpaths=["Chernovaya_D16"], name="NC1", number=1)))
    assert not _handle_problems(pm_edit.edit_macro(
        [pm_edit.SpeedFeed(toolpath="Chernovaya_D16", spindle=2980, feed=950)]))
    for text in (pm_macro.test_macro(), pm_macro.ask_macro(), pm_macro.snapshot_macro()):
        assert not _handle_problems(text)


def test_parts_and_check_macros_never_reuse_a_handle_name():
    """Имена дескрипторов не повторяются между частями и макросами одного потока."""
    import re

    from src import pm_check, pm_operation

    operation = pm_operation.OperationPlan(toolpath_name="C", tool_name="D16",
                                          rpm=2980, feed=950, calculate=True)
    texts = [part.text("h") for part in pm_operation.build_parts(operation)]
    texts.append(pm_check.build_macro(pm_check.CheckPlan(toolpaths=["C"])))
    names: list[str] = []
    for text in texts:
        for command in text.splitlines():
            if "FILE OPEN" in command:
                names += re.findall(r"FOR \w+ AS (\w+)", command)
    assert len(names) == len(set(names))

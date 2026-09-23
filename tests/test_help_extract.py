"""Тесты извлечения текста из файлов справки (wrapped-files, HTML-структура)."""
from __future__ import annotations

from pathlib import Path

from src.help_extract import (
    decode_html,
    extract_page_text,
    html_to_structured_text,
    is_junk_page,
    js_string_literals,
    unescape_js,
    unwrap_wrapped_js,
)

FIXTURE = Path(__file__).parent / "fixture_help"


def test_decode_html_utf8_and_bom():
    assert decode_html("Привет".encode("utf-8")) == "Привет"
    assert decode_html("\ufeffПривет".encode("utf-8")) == "Привет"


def test_decode_html_cp1251():
    raw = '<meta charset="windows-1251">Привет'.encode("cp1251")
    assert "Привет" in decode_html(raw)


def test_unescape_js_basic_escapes():
    assert unescape_js(r"<div class=\"x\">") == '<div class="x">'
    assert unescape_js(r"строка\nвторая") == "строка\nвторая"
    assert unescape_js(r"\u0413\u0440\u0430\u043d\u0438\u0446\u0430") == "Граница"


def test_unescape_js_temp_escape_not_crashing():
    # \x20 и \/ и «неизвестный» escape
    assert unescape_js(r"a\x20b") == "a b"
    assert unescape_js(r"a\/b") == "a/b"


def test_js_string_literals_skips_comments_and_broken_strings():
    src = """
    // "не строка"
    /* "тоже не строка" */
    var a = "первая";
    var b = 'вторая';
    var c = "оборванная
    ";
    """
    values = [v for _s, _e, v in js_string_literals(src)]
    assert "первая" in values and "вторая" in values
    assert all("не строка" != v for v in values)


def test_unwrap_document_write():
    js = r'document.write("<div><h1>Заголовок</h1><p>Текст страницы.</p></div>");'
    html = unwrap_wrapped_js(js)
    assert "<h1>" in html and "Текст страницы" in html


def test_unwrap_concatenated_strings_with_unicode_escapes():
    js = (
        'var content = "<div><h1>\\u0413\\u0440\\u0430\\u043d\\u0438\\u0446\\u0430</h1>" +\n'
        '  "<p>Вторая часть текста.</p></div>";\n'
        'document.getElementById("c").innerHTML = content;'
    )
    html = unwrap_wrapped_js(js)
    assert "Граница" in html
    assert "Вторая часть текста" in html


def test_unwrap_appends_multiple_writes():
    js = (
        "document.write('<div><p>Первый блок текста страницы.</p></div>');\n"
        "document.write('<div><p>Второй блок текста страницы.</p></div>');"
    )
    html = unwrap_wrapped_js(js)
    assert "Первый блок" in html and "Второй блок" in html


def test_unwrap_returns_empty_for_pure_code():
    assert unwrap_wrapped_js("function f() { return 1; }") == ""


def test_structured_text_keeps_headings_lists_tables_images():
    html = (
        "<div id='br'>Навигация</div>"
        "<h1>Чистовая обработка</h1>"
        "<p>Описание стратегии.</p>"
        "<ul><li>Первый шаг</li><li>Второй шаг</li></ul>"
        "<table><tr><th>Параметр</th><th>Значение</th></tr>"
        "<tr><td>Side step</td><td>1.5</td></tr></table>"
        "<img src='../images/a.png' alt='Диалог Swarf'>"
        "<script>alert('нет')</script>"
    )
    text = html_to_structured_text(html)
    assert "# Чистовая обработка" in text
    assert "- Первый шаг" in text
    assert "| Параметр | Значение |" in text
    assert "| Side step | 1.5 |" in text
    assert "[рисунок: Диалог Swarf]" in text
    assert "alert" not in text


def test_structured_text_removes_breadcrumbs_and_nav():
    html = (
        "<div class='breadcrumbs'>Главная > Справка</div>"
        "<div class='refbody'><p>Полезный текст про стратегию обработки.</p></div>"
        "<div class='copyright'>© Autodesk</div>"
    )
    text = html_to_structured_text(html)
    assert "Полезный текст" in text
    assert "Главная" not in text
    assert "Autodesk" not in text


def test_extract_page_text_from_stub_and_wrapped():
    title, text = extract_page_text(
        (FIXTURE / "l.rus" / "wrapped-files" / "GUID-0001.htm.js").read_bytes(),
        FIXTURE / "l.rus" / "wrapped-files" / "GUID-0001.htm.js",
    )
    assert title == "Чистовая обработка по кривой"
    assert "Swarf" in text
    assert "Создайте границу" in text


def test_extract_page_text_from_plain_html():
    title, text = extract_page_text(
        (FIXTURE / "l.rus" / "files" / "GUID-0004.htm").read_bytes(),
        FIXTURE / "l.rus" / "files" / "GUID-0004.htm",
    )
    # «PowerMill: » — служебный префикс из <title>, он обрезается
    assert title == "Установка домашней папки"
    assert "Параметры" in text


def test_is_junk_page():
    assert is_junk_page("")
    assert is_junk_page("коротко")
    assert not is_junk_page("Достаточно длинный текст страницы справки " * 3)

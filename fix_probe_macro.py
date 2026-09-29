"""Макрос разведки: пишет файл (а не только в окно сообщений) + видимое окно в конце."""
import pathlib

p = pathlib.Path("/home/user/powermill/src/power_mill_link.py")
s = p.read_text(encoding="utf-8")

start = s.index('PROBE_MACRO = """')
end = s.index('# --------------------------------------------------------------------------\n# Разведка (только чтение, ничего не меняет)')
new = '''# Разделы, которые печатает макрос разведки: (заголовок, папка PowerMill)
PROBE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("MODELS:", "Model"),
    ("BOUNDARIES:", "Boundary"),
    ("TOOLS:", "Tool"),
    ("TOOLPATHS:", "Toolpath"),
    ("WORKPLANES:", "Workplane"),
    ("NC PROGRAMS:", "NCProgram"),
    ("STOCK MODELS:", "StockModel"),
    ("PATTERNS:", "Pattern"),
)


def _pml_text(path: Path) -> str:
    """Путь для PML-строки: windows-разделители, обратные слэши не удваиваем."""
    text = str(path)
    if len(text) > 1 and text[1] == ":":
        return text.replace("/", "\\\\")
    return text


def probe_macro(output_file: Path | str | None = None) -> str:
    """Текст макроса разведки.

    Важное отличие от первых версий: макрос **пишет файл**, а не только печатает
    в окно сообщений PowerMill (оно может быть скрыто — тогда выглядит так, будто
    макрос «ничего не делает»). В конце показывается окно с результатом.
    """
    target = Path(output_file) if output_file else Path("output") / "pm_project.txt"
    out = _pml_text(target)

    body: list[str] = [
        "// ============================================================",
        "//  РАЗВЕДКА PowerMill AI",
        "//  Запуск: PowerMill -> вкладка «Макрос» -> Выполнить -> этот файл",
        "//  Макрос ничего не меняет: только читает списки объектов.",
        "// ============================================================",
        "",
        f"STRING $outfile = '{out}'",
        "FILE OPEN $outfile FOR WRITE AS out",
        'FILE WRITE "--- POWERMILL AI PROBE START ---" TO out',
        "",
        'PRINT "--- POWERMILL AI PROBE START ---"',
    ]
    for header, folder in PROBE_SECTIONS:
        body.append("")
        body.append(f'PRINT "{header}"')
        body.append(f'FILE WRITE "{header}" TO out')
        body.append(f'FOREACH $item IN FOLDER("{folder}") {{')
        body.append("    PRINT $item.name")
        body.append("    FILE WRITE $item.name TO out")
        body.append("}")

    body += [
        "",
        'PRINT "--- POWERMILL AI PROBE END ---"',
        'FILE WRITE "--- POWERMILL AI PROBE END ---" TO out',
        "FILE CLOSE out",
        "",
        'PRINT "Готово. Снимок записан: " + $outfile',
        'MESSAGE INFO "Разведка PowerMill AI закончена." + crlf + crlf + '
        '"Снимок проекта записан в файл:" + crlf + $outfile + crlf + crlf + '
        '"Что дальше: запусти пункт 24 меню — ассистент разберёт этот файл."',
        "",
    ]
    return "\\n".join(body)


# Совместимость: текст макроса с путём по умолчанию
PROBE_MACRO = probe_macro()


'''
s = s[:start] + new + s[end:]

# write_probe_macro пишет уже собранный для нужной папки макрос
old_start = s.index("def write_probe_macro(")
old_end = s.index("def main() -> int:")
new_fn = '''def write_probe_macro(folder: Path) -> Path:
    """Пишет макрос разведки в папку output (путь к файлу — внутри макроса)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "PM_PROBE.mac"
    target = folder / "pm_project.txt"
    path.write_text(probe_macro(target), encoding="utf-8")
    return path


'''
s = s[:old_start] + new_fn + s[old_end:]
p.write_text(s, encoding="utf-8")
print("макрос разведки переписан")

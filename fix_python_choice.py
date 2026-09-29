"""Один и тот же выбор Python во всех батниках + правки по логам пользователя."""
import pathlib
import re

ROOT = pathlib.Path("/home/user/powermill")

VENV_LINES = (
    'if exist ".venv\\Scripts\\python.exe" set "PY=.venv\\Scripts\\python.exe"\n'
    'if exist "venv\\Scripts\\python.exe" set "PY=venv\\Scripts\\python.exe"\n'
)

fixed: list[str] = []
for path in sorted(list(ROOT.glob("*.bat")) + list((ROOT / "scripts").glob("*.bat"))):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if 'set "PY=python"' not in text:
        continue

    lines = text.split("\n")
    out: list[str] = []
    seen_env = seen_venv = False
    for line in lines:
        stripped = line.strip()
        if stripped == 'set "PY=python"':
            out.append(line)
            continue
        if ".venv\\Scripts\\python.exe" in line and stripped.startswith("if exist"):
            if not seen_env:
                out.append('if exist ".venv\\Scripts\\python.exe" set "PY=.venv\\Scripts\\python.exe"')
                seen_env = True
            continue
        if "venv\\Scripts\\python.exe" in line and stripped.startswith("if exist"):
            if not seen_venv:
                out.append('if exist "venv\\Scripts\\python.exe" set "PY=venv\\Scripts\\python.exe"')
                seen_venv = True
            continue
        out.append(line)

    # если строк не было вовсе — вставляем блок сразу после set "PY=python"
    if not seen_env and not seen_venv:
        text2 = "\n".join(out).replace('set "PY=python"\n',
                                       'set "PY=python"\n' + VENV_LINES, 1)
        out = text2.split("\n")

    new = "\n".join(out)
    if new != text:
        path.write_bytes(new.encode("utf-8"))
        fixed.append(path.name)

print("исправлено батников:", len(fixed))
for name in fixed:
    print("  ", name)

# --- SyntaxWarning: docstring с обратными слэшами ---
p = ROOT / "src/pm_macro.py"
s = p.read_text(encoding="utf-8")
s = s.replace('''def _win_path(path) -> str:
    """Путь в стиле Windows''', '''def _win_path(path) -> str:
    r"""Путь в стиле Windows''')
p.write_text(s, encoding="utf-8")

# --- сообщение про pywin32: показываем, каким питоном работаем ---
p = ROOT / "src/pm_com.py"
s = p.read_text(encoding="utf-8")
s = s.replace('''    if _win32com is None:
        return None, ("pywin32 не установлен. Поставить: пункт 27 меню "
                      "(или pip install pywin32)")''',
'''    if _win32com is None:
        import sys

        return None, (f"pywin32 не установлен в этом Python: {sys.executable}\\n"
                      "   Поставить: пункт 27 меню (он ставит пакеты в тот же "
                      "интерпретатор).")''')
p.write_text(s, encoding="utf-8")
print("готово")

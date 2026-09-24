"""
Генератор PML-макросов: кнопка «PowerMill AI» внутри PowerMill.

Почему макрос, а не плагин
--------------------------
Плагин — это .NET-сборка, регистрация через regasm и своя разработка. Но
PowerMill умеет и сам, стандартными командами PML:

    FILE OPEN $path FOR WRITE AS out     // писать файлы
    FILE WRITE $text TO out
    FILE CLOSE out
    FILE OPEN $path FOR READ AS inp      // читать файлы
    FILE READ $lines FROM inp
    OLE FILEACTION 'OPEN' $bat           // запустить внешнюю программу
    INPUT CHOICE $list "вопрос"          // меню выбора
    INPUT "вопрос"                       // ввод строки
    MACRO PAUSE "текст"                  // пауза с кнопкой RESUME
    MESSAGE INFO $text                   // окно сообщения

Этого достаточно, чтобы ассистент жил внутри PowerMill: макрос спрашивает
технолога, кладёт запрос в файл, запускает наш скрипт, ждёт и показывает ответ
в окне PowerMill. Никаких сборок, регистраций и прав администратора.

Каждая конструкция в макросах взята из официального руководства Autodesk
«PowerMill Macro Programming Guide» или с официального форума Autodesk —
ничего не выдумано (см. src/pml_vocab.py, тесты проверяют макрос словарём).
"""
from __future__ import annotations

from pathlib import Path

from config import DATA_ROOT, OUTPUT_DIR

MACRO_DIR = OUTPUT_DIR / "pm_macros"
REQUEST_FILE = OUTPUT_DIR / "pm_request.txt"
ANSWER_FILE = OUTPUT_DIR / "pm_answer.txt"
PROJECT_FILE = OUTPUT_DIR / "pm_project.txt"
TEST_FILE = OUTPUT_DIR / "pm_test.txt"

# Куда технолог кладёт файл ответа/вопроса (пути внутри макроса)
MODES = (
    ("ask", "Спросить справку PowerMill"),
    ("macro", "Сгенерировать PML-макрос"),
    ("error", "Разобрать ошибку PowerMill"),
    ("cutting", "Режимы резания (материал + фреза)"),
)


def _win_path(path) -> str:
    """Путь в стиле Windows: разделители — обратные слэши.

    Зачем: пути попадают и в PML-макрос, и в .bat. На Windows Path сам даёт
    `\`, но если путь пришёл из настроек с `/` (или мы собираем его в другом
    окружении), получается смесь `E:\powermill-ai\output/pm_test.txt`. cmd её
    терпит, но PML-строка должна быть обычным windows-путём — поэтому
    нормализуем.

    Обратные слэши НЕ удваиваем: в PML `\` внутри строки — обычный символ, так
    пишут и в принятых решениях на форуме Autodesk:
    `OLE FILEACTION 'OPEN' 'C:\Program Files\...\Rhino.exe'`,
    `STRING path_file = "C:\temp\macropaths"`.
    """
    text = str(path)
    looks_windows = (len(text) > 1 and text[1] == ":") or "\\" in text
    return text.replace("/", "\\") if looks_windows else text


def ask_macro() -> str:
    """Макрос-пульт: спросить ассистента, не выходя из PowerMill."""
    modes_list = ", ".join(f'"{title}"' for _code, title in MODES)
    request = _win_path(REQUEST_FILE)
    answer = _win_path(ANSWER_FILE)
    launcher = _win_path(OUTPUT_DIR / "pm_answer.bat")

    return f"""// ============================================================
//  PowerMill AI — ассистент внутри PowerMill
//  Запуск: вкладка «Макрос» -> Выполнить -> этот файл
//  (или повесь на кнопку: см. пункт 28 меню)
// ============================================================

// 1. Спрашиваем, что нужно технологу
STRING LIST $modes = {{{modes_list}}}
INT $mode = INPUT CHOICE $modes "PowerMill AI: что нужно?"

// 2. Просим текст вопроса/задачи
STRING $question = INPUT "Введите вопрос или текст задачи:"
IF $question == '' {{
    MESSAGE WARN "Пустой запрос — ассистент сообщит об этом."
    $question = "(пустой запрос)"
}}

// 3. Пишем запрос в файл (его прочитает ассистент)
STRING $reqfile = '{request}'
FILE OPEN $reqfile FOR WRITE AS req
FILE WRITE "MODE=" + STRING($mode) TO req
FILE WRITE $question TO req
FILE CLOSE req

// 4. Запускаем ассистента (он посчитает ответ и запишет файл)
OLE FILEACTION 'OPEN' '{launcher}'

// 5. Ждём технолога: он видит окно ассистента и нажимает RESUME
MACRO PAUSE "Ассистент готовит ответ. Когда в окне ассистента появится 'Ответ готов', нажми RESUME."

// 6. Показываем ответ прямо в PowerMill
STRING $ansfile = '{answer}'
STRING LIST $lines = {{}}
FILE OPEN $ansfile FOR READ AS ans
FILE READ $lines FROM ans
FILE CLOSE ans
STRING $text = ""
FOREACH $l IN $lines {{
    $text = $text + $l + crlf
}}
PRINT $text
MESSAGE INFO $text
"""


def snapshot_macro() -> str:
    """Макрос-снимок: собрать данные проекта в файл и отдать ассистенту."""
    project = _win_path(PROJECT_FILE)
    launcher = _win_path(OUTPUT_DIR / "pm_snapshot.bat")

    return f"""// ============================================================
//  PowerMill AI — снимок проекта
//  Ассистент узнает имена моделей, границ, инструментов, траекторий.
//  Запуск: вкладка «Макрос» -> Выполнить -> этот файл
// ============================================================

STRING $outfile = '{project}'
FILE OPEN $outfile FOR WRITE AS out

FILE WRITE "MODELS:" TO out
FOREACH $item IN FOLDER("Model") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "BOUNDARIES:" TO out
FOREACH $item IN FOLDER("Boundary") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "TOOLS:" TO out
FOREACH $item IN FOLDER("Tool") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "TOOLPATHS:" TO out
FOREACH $item IN FOLDER("Toolpath") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "WORKPLANES:" TO out
FOREACH $item IN FOLDER("Workplane") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "NC PROGRAMS:" TO out
FOREACH $item IN FOLDER("NCProgram") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "STOCK MODELS:" TO out
FOREACH $item IN FOLDER("StockModel") {{
    FILE WRITE $item.name TO out
}}

FILE WRITE "PATTERNS:" TO out
FOREACH $item IN FOLDER("Pattern") {{
    FILE WRITE $item.name TO out
}}

FILE CLOSE out

PRINT "Снимок проекта сохранён: " + $outfile
OLE FILEACTION 'OPEN' '{launcher}'
"""


def test_macro() -> str:
    """Самопроверка моста: файлы + запуск программы + пауза.

    Как проверяется запуск программы без догадок: макрос сам пишет файл с
    текстом-ожиданием, внешний .bat перезаписывает его своим подтверждением, а
    макрос читает файл и сравнивает. Если текст не изменился — программа не
    запустилась. Никаких проверок существования файла, которых нет в PML.
    """
    test_file = _win_path(TEST_FILE)
    launcher = _win_path(OUTPUT_DIR / "pm_test.bat")

    return f"""// ============================================================
//  PowerMill AI — самопроверка моста (запусти этот макрос первым)
//  Проверяет: запись файла, чтение файла, запуск программы, пауза.
// ============================================================

// --- 1. Пишем файл из PowerMill ---
STRING $f = '{test_file}'
FILE OPEN $f FOR WRITE AS out
FILE WRITE "WAIT" TO out
FILE CLOSE out
PRINT "[1/4] Файл записан из PowerMill: " + $f

// --- 2. Читаем его обратно ---
STRING LIST $lines = {{}}
FILE OPEN $f FOR READ AS inp
FILE READ $lines FROM inp
FILE CLOSE inp
STRING $text = ""
FOREACH $l IN $lines {{
    $text = $text + $l
}}
PRINT "[2/4] Файл прочитан обратно, содержимое: " + $text

// --- 3. Запускаем внешнюю программу (наш .bat) ---
STRING $launcher = '{launcher}'
OLE FILEACTION 'OPEN' $launcher

// --- 4. Пауза: технолог видит тестовое окно и нажимает RESUME ---
MACRO PAUSE "Открылось окно 'ТЕСТ МОСТА'? Нажми RESUME."

// --- 5. Читаем файл ещё раз: программа должна была его перезаписать ---
STRING LIST $after = {{}}
FILE OPEN $f FOR READ AS inp2
FILE READ $after FROM inp2
FILE CLOSE inp2
STRING $after_text = ""
FOREACH $l IN $after {{
    $after_text = $after_text + $l
}}

PRINT "[3/4] Содержимое после запуска программы: " + $after_text

IF $after_text == $text {{
    MESSAGE WARN "МОСТ РАБОТАЕТ ЧАСТИЧНО: PowerMill пишет и читает файлы, но внешняя программа не запустилась или не перезаписала файл. Проверь, что pm_test.bat открывается двойным кликом."
    PRINT "[4/4] Запуск внешней программы: НЕ РАБОТАЕТ"
    PRINT "Файл-запускатель: " + $launcher
}} ELSE {{
    MESSAGE INFO "МОСТ РАБОТАЕТ ПОЛНОСТЬЮ: PowerMill записал файл, прочитал его, запустил внешнюю программу, и она ответила. Теперь можно запускать PM_AI_ASK.mac — ассистент внутри PowerMill."
    PRINT "[4/4] Запуск внешней программы: РАБОТАЕТ"
}}
"""


def launchers() -> dict[str, str]:
    """Батники, которые запускает PowerMill (через OLE FILEACTION)."""
    return {
        "pm_test.bat": f"""@echo off
chcp 65001 >nul
title ТЕСТ МОСТА — PowerMill видит внешнюю программу
cd /d "{_win_path(DATA_ROOT)}"
echo ТЕСТ МОСТА: окно открылось — значит PowerMill запустил программу.
echo.
echo Отвечаю PowerMill и жду кнопку RESUME...
echo POWERMILL-AI-OK> "{_win_path(TEST_FILE)}"
echo %DATE% %TIME%>> "{_win_path(TEST_FILE)}"
echo.
echo Ответ записан: {_win_path(TEST_FILE)}
echo Переключись в PowerMill и нажми RESUME.
pause
""",
        "pm_answer.bat": f"""@echo off
chcp 65001 >nul
title PowerMill AI - ответ на запрос из PowerMill
cd /d "{_win_path(DATA_ROOT)}"
set "PY=python"
if exist ".venv\\Scripts\\python.exe" set "PY=.venv\\Scripts\\python.exe"
if exist "venv\\Scripts\\python.exe" set "PY=venv\\Scripts\\python.exe"
"%PY%" -m scripts.pm_answer
echo.
echo [ГОТОВО] Ответ записан в {_win_path(ANSWER_FILE)}
echo Закрой это окно и нажми RESUME в PowerMill.
pause
""",
        "pm_snapshot.bat": f"""@echo off
chcp 65001 >nul
title PowerMill AI - снимок проекта из PowerMill
cd /d "{_win_path(DATA_ROOT)}"
set "PY=python"
if exist ".venv\\Scripts\\python.exe" set "PY=.venv\\Scripts\\python.exe"
if exist "venv\\Scripts\\python.exe" set "PY=venv\\Scripts\\python.exe"
"%PY%" -m scripts.load_project --auto
echo.
echo [ГОТОВО] Снимок проекта разобран.
pause
""",
    }


def write_all(folder: Path | None = None) -> list[Path]:
    """Пишет макросы и батники-запускатели. Возвращает список файлов."""
    folder = Path(folder or MACRO_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for name, text in (("PM_AI_ASK.mac", ask_macro()),
                       ("PM_AI_SNAPSHOT.mac", snapshot_macro()),
                       ("PM_AI_TEST.mac", test_macro())):
        path = folder / name
        # макросы PowerMill ждут обычные переводы строк
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        written.append(path)

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    for name, text in launchers().items():
        path = OUTPUT_DIR / name
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        written.append(path)

    return written


def power_mill_macro_folders() -> list[Path]:
    """Папки PowerMill, куда можно положить макрос (lib\\macro и пользовательская)."""
    from src.power_mill_link import find_install_dirs

    found: list[Path] = []
    for install in find_install_dirs():
        for relative in ("lib/macro", "lib/macros", "file/macro"):
            candidate = install / relative
            if candidate.exists() and candidate not in found:
                found.append(candidate)

    import os

    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        for version in ("2026", "2025", ""):
            candidate = (Path(base) / "Autodesk" / "PowerMill" /
                         (version if version else "") / "macro")
            if candidate.exists() and candidate not in found:
                found.append(candidate)
    return found


def main() -> int:
    """Написать макросы и запускатели (для отладки; в меню — пункт 28)."""
    written = write_all()
    print("Записано:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

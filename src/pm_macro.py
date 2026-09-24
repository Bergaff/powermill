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
from src import pml_files

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
    r"""Путь для .bat и для OLE FILEACTION: разделители — обратные слэши.

    Зачем: пути попадают и в PML-макрос, и в .bat. На Windows Path сам даёт
    `\`, но если путь пришёл из настроек с `/` (или мы собираем его в другом
    окружении), получается смесь `E:\powermill-ai\output/pm_test.txt`. cmd её
    терпит, но .bat-строке нужен обычный windows-путь — поэтому нормализуем.

    Обратные слэши НЕ удваиваем: в PML `\` внутри строки — обычный символ, так
    пишут и в принятых решениях на форуме Autodesk:
    `OLE FILEACTION 'OPEN' 'C:\Program Files\...\Rhino.exe'`.
    """
    text = str(path)
    looks_windows = (len(text) > 1 and text[1] == ":") or "\\" in text
    return text.replace("/", "\\") if looks_windows else text


def pml_path(path) -> str:
    """Путь для команд FM PmL (FILE OPEN / FILE READ): прямые слэши.

    Отличие от `_win_path` не косметическое. В окне сообщений живого
    PowerMill 2026 макрос с путём `E:\\powermill-ai\\...` в `FILE OPEN` вместо
    открытия файла показал приглашение «Выберите файл >» — то есть путь не
    разобрался. PowerMill сам отдаёт пути через `/` (`project_pathname(0)`), и
    рабочие макросы с форума открывают файлы так же:
    `FILE OPEN "S:/Templates/tool.pmlent" FOR WRITE AS output`.
    Windows понимает оба разделителя, поэтому для макросов берём `/`, а для
    .bat оставляем `_win_path`.
    """
    return str(path).replace("\\", "/")


def ask_macro() -> str:
    """Макрос-пульт: спросить ассистента, не выходя из PowerMill."""
    modes_list = ", ".join(f'"{title}"' for _code, title in MODES)
    request = pml_path(REQUEST_FILE)
    answer = pml_path(ANSWER_FILE)
    launcher = _win_path(OUTPUT_DIR / "pm_answer.bat")

    return f"""// ============================================================
//  PowerMill AI — ассистент внутри PowerMill
//  Запуск: вкладка «Макрос» -> Выполнить -> этот файл
//  (или повесь на кнопку: см. пункт 28 меню)
// ============================================================

// Переменные в PowerMill живут до конца сессии — сбрасываем перед работой,
// иначе второй запуск макроса падает на «local variable is already defined».
RESET LOCALVARS

// 1. Спрашиваем, что нужно технологу
STRING LIST $modes = {{{modes_list}}}
INT $mode = INPUT CHOICE $modes "PowerMill AI: что нужно?"

// 2. Просим текст вопроса/задачи
STRING $question = INPUT "Введите вопрос или текст задачи:"
IF $question == '' {{
    STRING $pm_empty = "Пустой запрос — ассистент сообщит об этом."
    MESSAGE WARN $pm_empty
    $question = "(пустой запрос)"
}}

// 2б. Если выбраны режимы резания (пункт 4 меню, номер 3) — сразу спрашиваем
//     материал и фрезу. Иначе ассистент считает «сталь среднеуглеродистую» и
//     диаметр по умолчанию, и в ответе появляется «материал не распознан».
IF $mode == 3 {{
    STRING $pm_material = INPUT "Материал (например: сталь 40Х, 12Х18Н10Т, Д16Т):"
    STRING $pm_tool = INPUT "Фреза: диаметр и число зубьев (например: D12 z4):"
    IF $pm_material != '' {{
        $question = $question + "; материал " + $pm_material
    }}
    IF $pm_tool != '' {{
        $question = $question + "; фреза " + $pm_tool
    }}
}}

// 3. Пишем запрос в файл (его прочитает ассистент)
//    ВАЖНО: в FILE WRITE уходит ГОТОВАЯ переменная, а не выражение со склейкой.
//    На живом PowerMill 2026 строка `FILE WRITE "MODE=" + STRING($mode) TO req`
//    останавливала макрос ровно на этом месте (видно в логе консоли 24.09),
//    поэтому текст собираем отдельной командой.
STRING $reqfile = '{request}'
STRING $mode_line = "MODE=" + STRING($mode)
FILE OPEN $reqfile FOR WRITE AS askq
FILE WRITE $mode_line TO askq
FILE WRITE $question TO askq
FILE CLOSE askq

// 4. Запускаем ассистента (он посчитает ответ и запишет файл)
OLE FILEACTION 'OPEN' '{launcher}'

// 5. Ждём технолога: он видит окно ассистента и нажимает RESUME
STRING $pm_wait_msg = "Ассистент готовит ответ. Когда в окне ассистента появится 'Ответ готов', нажми RESUME."
MACRO PAUSE $pm_wait_msg

// 6. Показываем ответ прямо в PowerMill
STRING $ansfile = '{answer}'
STRING LIST $lines = {{}}
FILE OPEN $ansfile FOR READ AS aska
FILE READ $lines FROM aska
FILE CLOSE aska
STRING $text = ""
FOREACH $l IN $lines {{
    $text = $text + $l + crlf
}}
PRINT $text
MESSAGE INFO $text
"""


def snapshot_macro() -> str:
    """Макрос-снимок: собрать данные проекта в файл и отдать ассистенту."""
    project = pml_path(PROJECT_FILE)
    launcher = _win_path(OUTPUT_DIR / "pm_snapshot.bat")

    return f"""// ============================================================
//  PowerMill AI — снимок проекта
//  Ассистент узнает имена моделей, границ, инструментов, траекторий.
//  Запуск: вкладка «Макрос» -> Выполнить -> этот файл
// ============================================================

RESET LOCALVARS

STRING $outfile = '{project}'
STRING $pm_head = "Файл снимка: " + $outfile
PRINT $pm_head
FILE OPEN $outfile FOR WRITE AS out

STRING $pm_sec = "MODELS:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("Model") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "BOUNDARIES:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("Boundary") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "TOOLS:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("Tool") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "TOOLPATHS:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("Toolpath") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "WORKPLANES:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("Workplane") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "NC PROGRAMS:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("NCProgram") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "STOCK MODELS:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("StockModel") {{
    FILE WRITE $item.name TO out
}}

STRING $pm_sec = "PATTERNS:"
FILE WRITE $pm_sec TO out
FOREACH $item IN FOLDER("Pattern") {{
    FILE WRITE $item.name TO out
}}

FILE CLOSE out

// Проверка: читаем файл обратно — доказательство, что снимок записан
// (в первых версиях макрос печатал текст, а файл не появлялся).
STRING LIST $pm_check_lines = {{}}
FILE OPEN $outfile FOR READ AS chk
FILE READ $pm_check_lines FROM chk
FILE CLOSE chk
INT $pm_count = SIZE($pm_check_lines)
STRING $pm_count_msg = "Строк в файле снимка: " + STRING($pm_count)
PRINT $pm_count_msg

IF $pm_count == 0 {{
    STRING $pm_bad = "Снимок НЕ записался (0 строк). Файл: " + $outfile
    $pm_bad = $pm_bad + crlf + "Пришли этот текст в чат — разберёмся."
    MESSAGE WARN $pm_bad
}}

// Отдаём снимок ассистенту: батник разберёт файл и обновит контекст проекта
OLE FILEACTION 'OPEN' '{launcher}'
"""


def trace_files() -> list[Path]:
    """Файлы-отметки шагов самопроверки: pm_trace_1.txt … pm_trace_5.txt.

    Зачем отдельный файл на каждый шаг: если макрос остановится на середине,
    по последнему появившемуся файлу сразу видно, ГДЕ это случилось. Проверить
    «есть ли файл» внутри PML нельзя (такой функции нет), а вот записать свой
    файл перед следующим шагом — можно.
    """
    return [OUTPUT_DIR / f"pm_trace_{index}.txt" for index in range(1, 6)]


def test_macro() -> str:
    """Самопроверка моста: файлы + запуск программы + пауза — по шагам.

    Как проверяется запуск программы без догадок: макрос сам пишет файл с
    текстом-ожиданием, внешний .bat перезаписывает его своим подтверждением, а
    макрос читает файл и сравнивает. Если текст не изменился — программа не
    запустилась. Никаких проверок существования файла, которых нет в PML.

    Вторая задача макроса — диагностика. На живом PowerMill 2026 макрос
    останавливался на записи в файл, и по логу консоли было непонятно, на каком
    именно шаге. Поэтому каждый шаг оставляет свой файл (pm_trace_1.txt …
    pm_trace_5.txt) и печатает короткую строку «powermill ai: шаг N ок».
    Последняя отметка = последний работающий шаг, а следующая строка макроса —
    та самая проблемная команда.

    Третье правило живого PowerMill: **в FILE WRITE (и PRINT, и MACRO PAUSE)
    уходит только переменная**. Строка `FILE WRITE "WAIT" TO tf1` с текстом в
    кавычках дала «недопустимый элемент или команда» — во всех рабочих макросах
    с форума Autodesk в FILE WRITE передаётся переменная. Поэтому текст сначала
    присваивается строке, и уже она идёт в команду.
    """
    test_file = pml_path(TEST_FILE)
    launcher = _win_path(OUTPUT_DIR / "pm_test.bat")
    traces = [pml_path(path) for path in trace_files()]

    return f"""// ============================================================
//  PowerMill AI — самопроверка моста (запусти этот макрос первым)
//  Проверяет: запись файла, чтение файла, запуск программы, пауза.
//
//  Каждый шаг отмечается своим файлом pm_trace_1.txt … pm_trace_5.txt.
//  Если макрос остановится — по номеру последнего файла видно, где именно:
//  следующая строка макроса после последней отметки и есть проблемная команда.
//  Открыть отметки: пункт 29 меню («Показать отчёты»).
// ============================================================

RESET LOCALVARS

// --- Шаг 1. Пишем файл из PowerMill ---
STRING $f = '{test_file}'
STRING $pm_text = "WAIT"
FILE OPEN $f FOR WRITE AS tfile
FILE WRITE $pm_text TO tfile
FILE CLOSE tfile

STRING $t1 = '{traces[0]}'
STRING $pm_mark = "шаг 1: файл записан из PowerMill"
FILE OPEN $t1 FOR WRITE AS marka
FILE WRITE $pm_mark TO marka
FILE CLOSE marka
STRING $pm_m1 = "powermill ai: шаг 1 ок (запись файла)"
PRINT $pm_m1

// --- Шаг 2. Читаем его обратно ---
STRING LIST $lines = {{}}
FILE OPEN $f FOR READ AS tread
FILE READ $lines FROM tread
FILE CLOSE tread
STRING $text = ""
FOREACH $l IN $lines {{
    $text = $text + $l
}}

STRING $t2 = '{traces[1]}'
FILE OPEN $t2 FOR WRITE AS markb
FILE WRITE $text TO markb
FILE CLOSE markb
STRING $pm_m2 = "powermill ai: шаг 2 ок (чтение файла)"
PRINT $pm_m2

// --- Шаг 3. Запускаем внешнюю программу (наш .bat) ---
STRING $launcher = '{launcher}'
OLE FILEACTION 'OPEN' $launcher

STRING $t3 = '{traces[2]}'
STRING $pm_mark3 = "шаг 3: команда запуска внешней программы отправлена"
FILE OPEN $t3 FOR WRITE AS markc
FILE WRITE $pm_mark3 TO markc
FILE CLOSE markc
STRING $pm_m3 = "powermill ai: шаг 3 ок (запуск отправлен)"
PRINT $pm_m3

// --- Шаг 4. Пауза: технолог видит тестовое окно и нажимает RESUME ---
STRING $pm_ask = "Открылось окно 'ТЕСТ МОСТА'? Нажми RESUME."
MACRO PAUSE $pm_ask

STRING $t4 = '{traces[3]}'
STRING $pm_mark4 = "шаг 4: пауза пройдена (RESUME нажат)"
FILE OPEN $t4 FOR WRITE AS markd
FILE WRITE $pm_mark4 TO markd
FILE CLOSE markd
STRING $pm_m4 = "powermill ai: шаг 4 ок (пауза пройдена)"
PRINT $pm_m4

// --- Шаг 5. Читаем файл ещё раз: программа должна была его перезаписать ---
STRING LIST $after = {{}}
FILE OPEN $f FOR READ AS tfinal
FILE READ $after FROM tfinal
FILE CLOSE tfinal
STRING $after_text = ""
FOREACH $l IN $after {{
    $after_text = $after_text + $l
}}

STRING $t5 = '{traces[4]}'
FILE OPEN $t5 FOR WRITE AS marke
FILE WRITE $after_text TO marke
FILE CLOSE marke

STRING $pm_m5 = "powermill ai: шаг 5, содержимое после программы: " + $after_text
PRINT $pm_m5

IF $after_text == $text {{
    STRING $pm_warn = "МОСТ РАБОТАЕТ ЧАСТИЧНО: PowerMill пишет и читает файлы, но внешняя программа не запустилась или не перезаписала файл. Проверь, что pm_test.bat открывается двойным кликом, и посмотри pm_trace_3.txt (пункт 29 меню)."
    MESSAGE WARN $pm_warn
    STRING $pm_no = "Шаг 5: запуск внешней программы НЕ РАБОТАЕТ. Файл-запускатель: " + $launcher
    PRINT $pm_no
}} ELSE {{
    STRING $pm_ok = "МОСТ РАБОТАЕТ ПОЛНОСТЬЮ: PowerMill записал файл, прочитал его, запустил внешнюю программу, и она ответила. Теперь можно запускать PM_AI_ASK.mac — ассистент внутри PowerMill."
    MESSAGE INFO $pm_ok
    STRING $pm_m6 = "powermill ai: шаг 5 ок (внешняя программа ответила)"
    PRINT $pm_m6
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

    # CP1251 и CRLF — так PowerMill читает русский текст без «кракозябр»
    for name, text in (("PM_AI_ASK.mac", ask_macro()),
                       ("PM_AI_SNAPSHOT.mac", snapshot_macro()),
                       ("PM_AI_TEST.mac", test_macro())):
        written.append(pml_files.write(folder / name, text))

    # батники — наоборот: UTF-8 (у них `chcp 65001`) и тоже CRLF
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

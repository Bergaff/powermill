"""
Разведка: чем можно подключиться к PowerMill на этом компьютере.

Зачем
-----
«Приложение для PowerMill» можно сделать тремя способами, и они очень разные
по сложности:

  A. PML-макросы + обмен файлами.
     Работает всегда: PowerMill сам умеет запускать .mac, а мы генерируем их
     и читаем то, что макрос печатает. Ничего доустанавливать не нужно.

  B. Внешняя программа, которая цепляется к ЗАПУЩЕННОМУ PowerMill через
     официальный API (Autodesk PowerShape & PowerMill API: .NET-сборки
     Autodesk.ProductInterface.PowerMILL) или COM. Даёт чтение проекта в
     реальном времени и выполнение команд. Нужны .NET-сборки, pywin32 или
     pythonnet.

  C. Полноценный плагин в интерфейсе PowerMill (окно внутри PowerMill:
     WPF-контролы Autodesk.WPFControls.ProductControls.PowerMILL, Visual
     Studio, регистрация плагина). Самое красивое и самое дорогое.

Этот модуль ничего не меняет в системе: он только смотрит, что уже есть,
и говорит, какой маршрут реально доступен.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Где обычно стоит PowerMill и его библиотеки
INSTALL_HINTS = (
    r"E:\powermill 2026\PowerMill 2026",
    r"C:\Program Files\Autodesk\PowerMill 2026",
    r"C:\Program Files\Autodesk\PowerMill 2025",
    r"C:\Program Files\Autodesk\PowerMill 2024",
)

# Сборки официального API: сначала новые имена (Autodesk), потом старые (Delcam)
API_ASSEMBLIES = (
    "Autodesk.ProductInterface.PowerMILL.dll",
    "Autodesk.WPFControls.ProductControls.PowerMILL.dll",
    "Autodesk.ProductInterface.PowerSHAPE.dll",
    "Delcam.ProductInterface.PowerMILL.dll",
    "Delcam.ProductInterface.dll",
)

# Куда PowerMill ставит макросы и служебные папки
MACRO_HINTS = (
    r"C:\ProgramData\Autodesk\PowerMill\2026\macros",
    r"C:\ProgramData\Autodesk\PowerMill\macros",
    r"C:\Users\Public\Documents\Autodesk\PowerMill 2026\macros",
)

KNOWN_PROGIDS = (
    "PowerMill.Application",
    "PowerMILL.Application",
    "Delcam.PowerMILL.Application",
    "PMApplication.Application",
)

# Имена процессов PowerMill: pmill.exe — сама программа (поэтому «powermill»
# в имени не всегда есть), рядом PowerMill.exe / PowerMillModeling.exe.
POWERMILL_PROCESS_HINTS = ("powermill", "pmill")

# Макрос-разведчик: печатает в окно сообщений PowerMill сведения о проекте и
# версии. Пользователь запускает его руками — это проверяет, что макросы
# вообще исполняются, и показывает, что именно видит PML.
# Разделы, которые печатает макрос разведки: (заголовок, папка PowerMill)
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
    """Путь для строки PML: как в самой PowerMill — с прямыми слэшами.

    Почему не обратные слэши: PowerMill сам возвращает пути через `/`
    (`project_pathname(0)`), и рабочие макросы с форума Autodesk открывают файлы
    ровно так: `FILE OPEN "S:/Templates/tool.pmlent" FOR WRITE AS output`.
    Обратный слэш в PML-строке ведёт себя по-разному в разных местах, а на
    живом PowerMill 2026 путь вида `E:\\powermill-ai\\...` заставил программу
    спрашивать «Выберите файл >» вместо того, чтобы открыть файл. Windows
    понимает оба разделителя, поэтому берём тот, в котором не сомневаемся.

    Обратные слэши остаются там, где путь идёт в .bat (там нужен windows-вид):
    см. `pm_macro._win_path`.
    """
    return str(path).replace("\\", "/")


def probe_macro(output_file: Path | str | None = None) -> str:
    """Текст макроса разведки.

    Три вещи, из-за которых первые версии «ничего не делали» (живой
    PowerMill 2026, разбор вывода из окна сообщений):

    1. макрос только печатал — окно сообщений может быть скрыто, поэтому теперь
       он ПИШЕТ ФАЙЛ и тут же читает его обратно, доказывая, что файл есть;
    2. повторный запуск макроса падает на «local variable is already defined»
       (переменные живут в сессии PowerMill) — первая строка теперь
       `RESET LOCALVARS`;
    3. путь с обратными слэшами PowerMill не разобрал и спросил
       «Выберите файл >» — путь пишем с прямыми слэшами (_pml_text).

    В конце макрос показывает окно: записан файл или нет.
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
        "// Переменные в PowerMill живут до конца сессии: без сброса второй",
        "// запуск макроса падает на «local variable is already defined».",
        "RESET LOCALVARS",
        "",
        f"STRING $pmout_file = '{out}'",
        'STRING $pmout_head = "Файл снимка: " + $pmout_file',
        "PRINT $pmout_head",
        "",
        "FILE OPEN $pmout_file FOR WRITE AS out",
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
        "// Проверка: читаем файл обратно. Это доказательство, что снимок есть,",
        "// а не «макрос что-то напечатал и ничего не сделал».",
        "STRING LIST $pmout_lines = {}",
        "FILE OPEN $pmout_file FOR READ AS chk",
        "FILE READ $pmout_lines FROM chk",
        "FILE CLOSE chk",
        "INT $pmout_count = SIZE($pmout_lines)",
        'STRING $pmout_count_msg = "Строк в файле снимка: " + STRING($pmout_count)',
        "PRINT $pmout_count_msg",
        "",
        "STRING $pmout_first = \"\"",
        "FILE OPEN $pmout_file FOR READ AS chk2",
        "FILE READ $pmout_first FROM chk2",
        "FILE CLOSE chk2",
        'STRING $pmout_first_msg = "Первая строка файла: " + $pmout_first',
        "PRINT $pmout_first_msg",
        "",
        'STRING $pmout_msg = "Разведка PowerMill AI закончена." + crlf + crlf',
        '$pmout_msg = $pmout_msg + "Файл снимка:" + crlf + $pmout_file + crlf',
        '$pmout_msg = $pmout_msg + "Строк в файле: " + STRING($pmout_count) + crlf',
        '$pmout_msg = $pmout_msg + "Первая строка: " + $pmout_first + crlf + crlf',
        '$pmout_msg = $pmout_msg + "Дальше: запусти пункт 24 меню — ассистент разберёт этот файл."',
        "IF $pmout_count == 0 {",
        '    PRINT "[ОШИБКА] Файл снимка пустой — пришли этот текст в чат."',
        '    $pmout_msg = $pmout_msg + crlf + "ФАЙЛ НЕ ЗАПИСАЛСЯ (0 строк). Пришли этот текст в чат."',
        "    MESSAGE WARN $pmout_msg",
        "} ELSE {",
        '    STRING $pmout_ok = "[OK] Снимок записан: " + $pmout_file',
        "    PRINT $pmout_ok",
        "    MESSAGE INFO $pmout_msg",
        "}",
        "",
    ]
    return "\n".join(body)


# Совместимость: текст макроса с путём по умолчанию
PROBE_MACRO = probe_macro()


# --------------------------------------------------------------------------
# Разведка (только чтение, ничего не меняет)
# --------------------------------------------------------------------------
def find_install_dirs(extra: list[str] | None = None) -> list[Path]:
    """Существующие папки установки PowerMill."""
    found: list[Path] = []
    for raw in list(INSTALL_HINTS) + list(extra or []):
        path = Path(raw)
        if path.exists():
            found.append(path)
    # рядом с установкой могут быть версии вида «PowerMill 2027»
    for parent in (Path(r"E:\powermill 2026"), Path(r"C:\Program Files\Autodesk")):
        if parent.exists():
            try:
                for child in parent.iterdir():
                    if child.is_dir() and "powermill" in child.name.lower():
                        if child not in found:
                            found.append(child)
            except OSError:
                pass
    return found


def find_api_assemblies(dirs: list[Path]) -> dict[str, list[str]]:
    """Ищет .NET-сборки официального API в папках установки.

    Возвращает {имя сборки: [где найдена, ...]}.
    """
    result: dict[str, list[str]] = {}
    for folder in dirs:
        try:
            for path in folder.rglob("*.dll"):
                name = path.name
                if name in API_ASSEMBLIES:
                    result.setdefault(name, []).append(str(path))
        except OSError:
            continue
    return result


def find_pm_executables(dirs: list[Path]) -> list[str]:
    """Исполняемые файлы PowerMill (по ним видно версию и путь)."""
    found: list[str] = []
    for folder in dirs:
        for pattern in ("PowerMill.exe", "powerMill.exe", "powermill.exe"):
            candidate = folder / pattern
            if candidate.exists():
                found.append(str(candidate))
        for pattern in ("*.exe",):
            try:
                for path in folder.glob(pattern):
                    if "powermill" in path.name.lower() and str(path) not in found:
                        found.append(str(path))
                        break
            except OSError:
                pass
    return found


def powermill_running() -> bool | None:
    """Запущен ли PowerMill сейчас. None — не смогли проверить.

    Почему два способа. Первый — посмотреть процессы, но имена разные:
    `pmill.exe` (сама PowerMill), `PowerMill.exe`, `PowerMillModeling.exe`.
    Если по имени ничего не нашли, всё равно есть шанс ошибиться, поэтому
    второй способ — спросить сам COM-объект: отвечает значит работает.
    На живом PowerMill в отчёте пользователя было «не запущен», хотя проект
    читался — именно из-за имени процесса.
    """
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if any(hint in name for hint in POWERMILL_PROCESS_HINTS):
                    return True
        except Exception:  # noqa: BLE001
            psutil = None
    return com_object_alive()


def com_object_alive() -> bool | None:
    """Отвечает ли COM-объект PowerMill (то есть запущена ли программа).

    GetActiveObject ничего не запускает: он только спрашивает уже работающий
    объект. None — проверить нельзя (не Windows или нет pywin32).
    """
    if os.name != "nt":
        return None
    try:
        import win32com.client
    except ImportError:
        return None
    for progid in KNOWN_PROGIDS:
        try:
            win32com.client.GetActiveObject(progid)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def python_bridges() -> dict[str, bool]:
    """Что доступно на стороне Python для разговора с PowerMill."""
    available: dict[str, bool] = {}
    for module, title in (("win32com.client", "pywin32 (COM)"),
                          ("clr", "pythonnet (.NET)")):
        try:
            __import__(module)
            available[title] = True
        except Exception:  # noqa: BLE001
            available[title] = False
    return available


def com_progids() -> list[str]:
    """Зарегистрированные COM-классы PowerMill (только Windows)."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    found: list[str] = []
    for hive in (winreg.HKEY_CLASSES_ROOT,):
        for progid in KNOWN_PROGIDS:
            try:
                with winreg.OpenKey(hive, progid):
                    found.append(progid)
            except OSError:
                continue
        # заодно посмотрим, нет ли похожих ключей
        try:
            with winreg.OpenKey(hive, "") as root:
                count = winreg.QueryInfoKey(root)[0]
                for index in range(min(count, 20000)):
                    try:
                        name = winreg.EnumKey(root, index)
                    except OSError:
                        continue
                    low = name.lower()
                    if "powermill" in low and name not in found and len(found) < 12:
                        found.append(name)
        except OSError:
            pass
    return found


def dotnet_versions() -> list[str]:
    """Установленные версии .NET Framework (нужны для сборок API)."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    versions: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as key:
            release, _ = winreg.QueryValueEx(key, "Release")
        table = ((533320, "4.8.1+"), (528040, "4.8"), (461808, "4.7.2"),
                 (394802, "4.6.2"), (378389, "4.5"))
        label = next((text for number, text in table if release >= number),
                     f"release {release}")
        versions.append(f".NET Framework {label}")
    except OSError:
        versions.append("нет записи о .NET Framework 4.x")
    return versions


def find_macro_folders() -> list[str]:
    """Существующие папки макросов PowerMill (куда класть наши .mac)."""
    return [raw for raw in MACRO_HINTS if Path(raw).exists()]


def collect() -> dict:
    """Собирает всё, что удалось узнать о машине (безопасно, только чтение)."""
    dirs = find_install_dirs()
    return {
        "platform": sys.platform,
        "install_dirs": dirs,
        "executables": find_pm_executables(dirs),
        "assemblies": find_api_assemblies(dirs),
        "running": powermill_running(),
        "bridges": python_bridges(),
        "progids": com_progids(),
        "dotnet": dotnet_versions(),
        "macro_folders": find_macro_folders(),
    }


# --------------------------------------------------------------------------
# Вывод: какой маршрут доступен
# --------------------------------------------------------------------------
def verdict(data: dict) -> list[dict]:
    """Превращает результаты разведки в заключения по маршрутам.

    Каждый маршрут: code, title, available, note и action (что сделать, если
    маршрут пока не открыт). Маршрут B специально выделен: если сборки API и
    COM-регистрация есть, а моста Python нет — это не «нельзя», а «осталось
    поставить мост» (пункт 27 меню).
    """
    routes: list[dict] = []

    # A. Макросы + файлы — работает, если PowerMill вообще установлен
    installed = bool(data.get("install_dirs") or data.get("executables"))
    routes.append({
        "code": "A",
        "title": "PML-макросы + файловый обмен",
        "available": installed,
        "note": ("готово и работает уже сейчас: ассистент пишет макрос, "
                 "ты запускаешь его в PowerMill") if installed else
                "PowerMill не найден — уточни папку установки",
        "action": "" if installed else "пункт 10 меню — задать путь к справке",
    })

    # B. Внешняя программа к запущенному PowerMill
    assemblies = data.get("assemblies") or {}
    bridges = data.get("bridges") or {}
    progids = data.get("progids") or []
    api_found = bool(assemblies)
    com_found = bool(progids)
    bridge_ready = any(bridges.values())

    if (api_found or com_found) and bridge_ready:
        note = ("API и COM есть, мост Python готов — можно читать проект "
                "в реальном времени")
        action = ""
    elif api_found and com_found:
        note = ("сборки API и COM-регистрация PowerMill найдены — "
                "не хватает только моста Python")
        action = "пункт 27 меню — поставить мост (pywin32 / pythonnet)"
    elif api_found:
        note = "сборки API найдены, моста Python нет"
        action = "пункт 27 меню — поставить мост (pywin32 / pythonnet)"
    elif com_found:
        note = f"есть COM-регистрация: {', '.join(progids[:3])}"
        action = "пункт 27 меню — поставить pywin32 и попробовать подключение"
    else:
        note = ("не видно ни сборок API, ни COM-регистрации PowerMill — "
                "маршрут требует установки API (NuGet) или другого выпуска")
        action = "остаёмся на маршруте A (пункты 23–24)"

    routes.append({
        "code": "B",
        "title": "Внешняя программа к запущенному PowerMill (API/COM)",
        "available": bool((api_found or com_found) and bridge_ready),
        "note": note,
        "action": action,
    })

    # C. Плагин с окном внутри PowerMill
    plugin_installers = [
        path for path in data.get("install_dirs", [])
        if any(word in str(path).lower()
               for word in ("robot", "additive", "project server", "vimill",
                            "ncsimul", "simulation analysis"))
    ]
    wpf = any("WPFControls" in name for name in assemblies)
    routes.append({
        "code": "C",
        "title": "Плагин-окно внутри PowerMill (.NET/WPF)",
        "available": False,          # всегда «позже»: нужна своя сборка
        "note": ("нужна своя сборка .NET и регистрация через regasm.exe; "
                 + ("установленные плагины Autodesk найдены — "
                    "есть на что опереться" if plugin_installers
                    else "сборок WPF не видно, потребуется SDK")),
        "action": "пункт 25 меню — найти каркас и примеры плагинов",
    })
    return routes


def format_report(data: dict) -> str:
    """Печатает понятный отчёт для технолога."""
    lines = ["=" * 62,
             "  РАЗВЕДКА: ЧЕМ МОЖНО ПОДКЛЮЧИТЬСЯ К PowerMill",
             "  Ничего не изменяется — только проверка того, что есть",
             "=" * 62, ""]

    lines.append("Что нашлось на компьютере:")
    dirs = data.get("install_dirs") or []
    lines.append(f"  Установка PowerMill: {len(dirs)}")
    for path in dirs:
        lines.append(f"    {path}")
    if data.get("executables"):
        lines.append("  Программы:")
        for path in data["executables"][:5]:
            lines.append(f"    {path}")

    assemblies = data.get("assemblies") or {}
    lines.append(f"  Сборки официального API: {len(assemblies)}")
    for name, places in list(assemblies.items())[:6]:
        lines.append(f"    {name}")
        lines.append(f"      {places[0]}")

    running = data.get("running")
    lines.append("  PowerMill сейчас: "
                 + ("запущен" if running else "не запущен" if running is False
                    else "не смог проверить"))
    if data.get("dotnet"):
        lines.append(f"  .NET: {', '.join(data['dotnet'])}")
    if data.get("progids"):
        lines.append(f"  COM-регистрация: {', '.join(data['progids'][:5])}")
    bridges = data.get("bridges") or {}
    if bridges:
        ready = [name for name, ok in bridges.items() if ok]
        lines.append("  Мост Python: " + (", ".join(ready) if ready
                                          else "нет (pywin32 / pythonnet не стоят)"))
    if data.get("macro_folders"):
        lines.append("  Папки макросов:")
        for folder in data["macro_folders"]:
            lines.append(f"    {folder}")

    lines += ["", "=" * 62, "  ЧТО ЭТО ЗНАЧИТ", "=" * 62]
    for route in verdict(data):
        if route["available"]:
            mark = "[МОЖНО]  "
        elif route["code"] == "C":
            mark = "[ПОЗЖЕ]  "
        else:
            mark = "[НЕЛЬЗЯ] "
        lines.append(f"  {mark}{route['code']}. {route['title']}")
        lines.append(f"            {route['note']}")
        if route.get("action"):
            lines.append(f"            → {route['action']}")
    lines.append("")
    return "\n".join(lines)


def write_probe_macro(folder: Path) -> Path:
    """Пишет макрос разведки в папку output (путь к файлу — внутри макроса).

    Переводы строк — windows-овские (CRLF), как у остальных наших макросов и
    как у макросов самой PowerMill.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "PM_PROBE.mac"
    target = folder / "pm_project.txt"
    text = probe_macro(target).replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    return path


def main() -> int:
    from config import OUTPUT_DIR

    data = collect()
    report = format_report(data)
    print(report)

    path = write_probe_macro(OUTPUT_DIR)

    lines: list[str] = [report, ""]
    if any(data.get("bridges", {}).values()):
        lines.append("Мост Python стоит — разведка API: пункт 27 меню (или /pm в чате).")
    else:
        lines.append("Дальше: пункт 27 меню — поставить мост к PowerMill (живое чтение проекта).")
    lines.append("")
    lines.append("Макрос-разведчик записан:")
    lines.append(f"  {path}")
    lines.append("")
    lines.append("Что сделать (один раз, 20 секунд):")
    lines.append("  1) открой PowerMill и нужный проект")
    lines.append("  2) вкладка «Макрос» (или Лента -> Макрос) -> Выполнить -> выбери файл")
    lines.append("  3) откроется окно сообщений: скопируй строки между")
    lines.append("     --- POWERMILL AI PROBE START --- и --- ... END ---")
    lines.append("  4) вставь их в ассистента (пункт 1 меню) — он посмотрит,")
    lines.append("     что видит PML в твоей установке")
    lines.append("")
    lines.append("Это проверяет сразу три вещи: исполняются ли макросы, какие папки")
    lines.append("видит PowerMill и как называются объекты в твоём проекте.")
    tail = "\n".join(lines[1:])
    print(tail)

    report_path = Path(OUTPUT_DIR) / "pm_link_report.txt"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print()
        print(f"Отчёт сохранён: {report_path}")
        print("Открыть его можно пунктом 29 меню («Показать отчёты»).")
    except OSError as error:
        print(f"(!) Не удалось сохранить отчёт: {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

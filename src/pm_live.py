"""
Живое подключение к запущенному PowerMill (шаг 2.1 плана).

Три стратегии, по порядку надёжности:

1. **dotnet** — официальный API Autodesk (`Autodesk.ProductInterface.PowerMILL.dll`
   или старые сборки Delcam) через pythonnet. Даёт доступ к проекту в реальном
   времени: модели, границы, инструменты, траектории, выполнение макросов.
2. **com** — PowerMill как COM-сервер через pywin32 (`win32com.client`).
   Работает там, где COM-регистрация есть, а сборок .NET под рукой нет.
3. **file** — обмен файлами: ассистент пишет макрос, ты запускаешь его в
   PowerMill, результат приносишь обратно (это работает всегда — см. пункт 24).

Важно: модуль НЕ угадывает устройство API. Он пробует подключиться и печатает
то, что реально нашёл на машине (имена свойств и методов объекта). Это и есть
разведка, по которой дальше пишется точная интеграция — вместо догадок.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Порядок попыток COM: от новых имён к старым
COM_PROGIDS = (
    "PowerMill.Application",
    "PowerMILL.Application",
    "Delcam.PowerMILL.Application",
    "PMApplication.Application",
)

# Сборки официального API: сначала новые имена, потом Delcam
DOTNET_ASSEMBLIES = (
    "Autodesk.ProductInterface.PowerMILL.dll",
    "Delcam.ProductInterface.PowerMILL.dll",
)

# Что хотим увидеть в объекте проекта (проверяем наличие, ничего не выдумываем)
PROJECT_ATTRS = {
    "models": ("Models", "ModelCollection"),
    "boundaries": ("Boundaries", "BoundaryCollection"),
    "tools": ("Tools", "ToolCollection"),
    "toolpaths": ("Toolpaths", "ToolpathCollection", "ToolPaths"),
    "workplanes": ("Workplanes", "WorkPlaneCollection", "WorkplanesCollection"),
    "ncprograms": ("NCPrograms", "NcPrograms", "NCProgramCollection"),
    "stockmodels": ("StockModels",),
    "patterns": ("Patterns",),
}


# --------------------------------------------------------------------------
# Что есть на машине
# --------------------------------------------------------------------------
def bridges() -> dict[str, bool]:
    """Мосты Python -> Windows: pythonnet (.NET) и pywin32 (COM)."""
    result: dict[str, bool] = {}
    for module, title in (("clr", "pythonnet (.NET)"), ("win32com.client", "pywin32 (COM)")):
        try:
            __import__(module)
            result[title] = True
        except Exception:  # noqa: BLE001
            result[title] = False
    return result


def find_api_assembly(extra_dirs: list[str] | None = None) -> str | None:
    """Путь к сборке официального API, если она есть на машине."""
    from src.power_mill_link import find_install_dirs

    folders = list(extra_dirs or []) + [str(p) for p in find_install_dirs()]
    # Сначала папки, где сборки API точно есть (Project Server, сама установка),
    # потом всё остальное: так поиск находит рабочий файл, а не первый попавшийся.
    def rank(folder: str) -> tuple[int, str]:
        low = folder.lower()
        if "project server" in low:
            return (0, low)
        if "powermill 2026" in low or "powermill 2025" in low:
            return (1, low)
        return (2, low)

    folders.sort(key=rank)
    for folder in folders:
        root = Path(folder)
        if not root.exists():
            continue
        for name in DOTNET_ASSEMBLIES:
            try:
                matches = list(root.rglob(name))
            except OSError:
                continue
            if matches:
                return str(matches[0])
    return None


# --------------------------------------------------------------------------
# Подключение
# --------------------------------------------------------------------------
def connect_dotnet(assembly: str | None = None) -> tuple[object | None, str]:
    """Попытка подключиться через официальный .NET API (pythonnet)."""
    try:
        import clr  # noqa: F401
    except Exception as error:  # noqa: BLE001
        return None, f"pythonnet не установлен ({error}). Установка: pip install pythonnet"

    assembly = assembly or find_api_assembly()
    if not assembly:
        return None, ("сборка Autodesk.ProductInterface.PowerMILL.dll не найдена. "
                      "Она появляется с PowerMill или ставится из NuGet "
                      "(Autodesk.ProductInterface.PowerMILL)")

    try:
        import clr

        clr.AddReference(assembly)
    except Exception as error:  # noqa: BLE001
        return None, f"не удалось загрузить сборку {assembly}: {error}"

    for module_name, class_name in (
        ("Autodesk.ProductInterface.PowerMILL", "PMAutomation"),
        ("Delcam.ProductInterface.PowerMILL", "PMAutomation"),
    ):
        try:
            module = __import__(module_name, fromlist=[class_name])
            automation_class = getattr(module, class_name)
        except Exception:  # noqa: BLE001
            continue
        for kwargs in ({"reuse": 1}, {"InstanceReuse": 1}, {}):
            try:
                automation = automation_class(**kwargs) if kwargs else automation_class()
                return automation, f"подключено через .NET API: {assembly}"
            except Exception:  # noqa: BLE001
                continue
    return None, ("сборка загружена, но класс PMAutomation не создался. "
                  "Пришли этот текст — добавим точный вызов.")


def connect_com(progids: tuple[str, ...] = COM_PROGIDS) -> tuple[object | None, str]:
    """Подключение к PowerMill как к COM-серверу (pywin32).

    Сначала пробуем **присоединиться** к уже запущенному PowerMill
    (`GetActiveObject`) — `Dispatch` в такой ситуации открывает вторую копию
    программы, а это технологу не нужно. Если PowerMill не запущен, честно
    говорим об этом: запускать его за пользователя мы не будем.
    """
    from src import pm_com

    app, message = pm_com.attach(progids)
    if app is not None:
        return app, message

    return None, message


def connect() -> tuple[object | None, str, str]:
    """Пробует стратегии по порядку. Возвращает (объект, стратегия, сообщение)."""
    api, message = connect_dotnet()
    if api is not None:
        return api, "dotnet", message

    com_api, com_message = connect_com()
    if com_api is not None:
        return com_api, "com", com_message

    return None, "file", (f"{message}\n   {com_message}\n"
                          "   Живое подключение пока недоступно — работаем "
                          "обменом файлами (пункт 24 меню), это надёжно.")


# --------------------------------------------------------------------------
# Разведка поверхности API
# --------------------------------------------------------------------------
def describe_surface(api: object, limit: int = 60) -> str:
    """Печатает, что реально умеет объект: свойства и методы.

    Это не догадка, а данные с конкретной машины: по ним пишется интеграция.
    """
    names = [n for n in dir(api) if not n.startswith("_")]
    interesting = [n for n in names if not n.startswith("__")]
    lines = [f"Объект подключения отвечает. Доступно {len(interesting)} имён."]
    lines.append("  " + ", ".join(interesting[:limit]))
    if len(interesting) > limit:
        lines.append(f"  … ещё {len(interesting) - limit}")

    # ищем проект
    for attr in ("ActiveProject", "Project", "ActiveDocument", "Document"):
        try:
            project = getattr(api, attr)
        except Exception:  # noqa: BLE001
            continue
        if project is not None:
            lines.append(f"Проект найден через {attr}.")
            project_names = [n for n in dir(project) if not n.startswith("_")]
            lines.append("  объекты проекта: " + ", ".join(project_names[:limit]))
            break
    return "\n".join(lines)


def _iter_collection(collection: object, limit: int = 500) -> list[str]:
    """Пытается получить имена объектов из коллекции API (не падая)."""
    names: list[str] = []
    try:
        count = int(getattr(collection, "Count", 0) or 0)
    except Exception:  # noqa: BLE001
        count = 0

    for index in range(min(count, limit)):
        for accessor in ("Item", "get_Item"):
            try:
                item = getattr(collection, accessor)(index)
            except Exception:  # noqa: BLE001
                continue
            name = None
            for attr in ("Name", "name"):
                try:
                    name = getattr(item, attr)
                    break
                except Exception:  # noqa: BLE001
                    continue
            if name:
                names.append(str(name))
            break

    if not names:
        try:
            for item in collection:            # некоторые коллекции перебираемы
                for attr in ("Name", "name"):
                    try:
                        names.append(str(getattr(item, attr)))
                        break
                    except Exception:  # noqa: BLE001
                        continue
                if len(names) >= limit:
                    break
        except Exception:  # noqa: BLE001
            pass
    return names


def project_objects(api: object) -> tuple[dict, str]:
    """Читает списки объектов проекта через API. Возвращает (данные, отчёт)."""
    project = None
    for attr in ("ActiveProject", "Project", "ActiveDocument", "Document"):
        try:
            candidate = getattr(api, attr)
        except Exception:  # noqa: BLE001
            continue
        if candidate is not None:
            project = candidate
            break
    if project is None:
        return {}, "проект не найден: открой проект в PowerMill (File -> Open)"

    data: dict[str, list[str]] = {}
    report: list[str] = []
    for section, attrs in PROJECT_ATTRS.items():
        for attr in attrs:
            try:
                collection = getattr(project, attr)
            except Exception:  # noqa: BLE001
                continue
            if collection is None:
                continue
            names = _iter_collection(collection)
            if names:
                data[section] = names
                report.append(f"  {section}: {len(names)}")
            else:
                report.append(f"  {section}: коллекция есть, имена прочитать не удалось")
            break
    if not data:
        report.append("  ни одну коллекцию прочитать не удалось — "
                      "пришли вывод, добавим рабочий способ")
    return data, "\n".join(report)


def run_macro(api: object, macro_path: str) -> str:
    """Пытается выполнить макрос в запущенном PowerMill."""
    path = Path(macro_path)
    if not path.exists():
        return f"(!) Файл макроса не найден: {path}"

    candidates = (
        ("ExecuteMacro", (str(path),)),
        ("RunMacro", (str(path),)),
        ("Execute", (str(path),)),
        ("DoCommand", (f'MACRO "{path}"',)),
    )
    for name, args in candidates:
        method = getattr(api, name, None)
        if method is None:
            continue
        try:
            method(*args)
            return f"✅ макрос выполнен через {name}: {path.name}"
        except Exception as error:  # noqa: BLE001
            return f"(!) {name} не сработал: {error}"
    return ("(!) Не нашёл способа запустить макрос через API. "
            "Запусти его в PowerMill вручную: вкладка Макрос -> Выполнить.")


# --------------------------------------------------------------------------
# Отчёт
# --------------------------------------------------------------------------
def status_report(verbose: bool = True) -> str:
    """Что доступно и что делать: короткий понятный отчёт."""
    lines = ["=" * 60,
             "  ЖИВОЕ ПОДКЛЮЧЕНИЕ К PowerMill",
             "=" * 60]

    available = bridges()
    lines.append("Мосты Python:")
    for title, ok in available.items():
        lines.append(f"  {'[есть]' if ok else '[НЕТ] '} {title}")
    if not any(available.values()):
        lines.append("  Как поставить: пункт 27 меню — «Поставить мост к PowerMill»")
        lines.append("  (он же сразу проверит подключение и покажет разведку API)")

    assembly = find_api_assembly()
    lines.append(f"Сборка API: {assembly or 'не найдена'}")

    from src.power_mill_link import powermill_running

    running = powermill_running()
    lines.append("PowerMill сейчас: " + ("запущен" if running else "не запущен"
                                        if running is False else "не смог проверить"))

    lines.append("")
    api, strategy, message = connect()
    lines.append(f"Подключение: {strategy}")
    lines.append(f"  {message}")
    if api is not None and verbose:
        lines.append("")
        lines.append(describe_surface(api))
        data, report = project_objects(api)
        lines.append("Объекты проекта:")
        lines.append(report)
        if data:
            lines.append("  Снимок получен — можно сохранить в контекст проекта "
                         "(пункт 24 либо команда /project в чате).")
    else:
        lines.append("")
        lines.append("Живое подключение не поднялось — это нормальный путь:")
        lines.append("  1) пункт 24 меню — загрузить снимок проекта через макрос;")
        lines.append("  2) пункт 25 меню — подготовить плагин PowerMill "
                     "(он работает внутри программы и не требует мостов).")
    return "\n".join(lines)


def main() -> int:
    args = sys.argv[1:]
    if "--save" in args:
        from src import project_context

        api, strategy, message = connect()
        print(f"Подключение: {strategy}\n  {message}")
        if api is None:
            return 2
        data, report = project_objects(api)
        print(report)
        if not data:
            return 3
        data["_source"] = f"живой API ({strategy})"
        path = project_context.save(data)
        print(f"💾 Снимок проекта сохранён: {path}")
        return 0

    print(status_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

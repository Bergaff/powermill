"""
Библиотеки: чего не хватает и как поставить недостающее одним действием.

Зачем отдельный модуль
----------------------
Про «поставь библиотеки» говорят сразу четыре места: окно приложения (пункт 39),
меню (пункт 43), установщик `install.bat` и проверка компьютера (пункт 40).
Если у каждого свой список — один экран говорит «всё есть», а другой «нет
requests». Поэтому список пакетов и проверка «что РЕАЛЬНО импортируется» живут
здесь, а все остальные берут их отсюда.

Два набора
----------
* `BASE_PACKAGES` — без них программа работает наполовину (и главное: **нет
  связи с PowerMill**). Ставятся вместе с приложением, ставятся одной кнопкой,
  ставятся пунктом 43. Это маленькие пакеты — десятки мегабайт.
* `OPTIONAL_PACKAGES` — тяжёлые (гигабайты) и нужны только для поиска по
  справке, смыслового поиска и разбора видео. Ставятся по желанию (ночью).

Проверка идёт по модулю, а не по имени пакета: у `pywin32` модуль называется
`win32com.client`, у `beautifulsoup4` — `bs4`. Это уже один раз дало ложное
«pywin32 не установлен» — поэтому здесь в первую очередь модуль.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from config import OUTPUT_DIR

REPORT_FILE = OUTPUT_DIR / "install_packages_report.txt"


@dataclass(frozen=True)
class PackageSpec:
    """Один пакет: что ставим, чем проверяем, зачем нужен."""

    package: str
    modules: tuple[str, ...]
    purpose: str
    heavy: bool = False


# --- без этого программа не работает полноценно ---------------------------
BASE_PACKAGES: tuple[PackageSpec, ...] = (
    PackageSpec("pywin32", ("win32com.client", "pythoncom"),
                "связь с PowerMill (пункты 23, 24, 31, 33-37, 41)"),
    PackageSpec("psutil", ("psutil",),
                "поиск запущенного PowerMill (пункты 23, 41)"),
    PackageSpec("requests", ("requests",), "обмен с ИИ по API"),
    PackageSpec("beautifulsoup4", ("bs4",), "разбор страниц справки"),
    PackageSpec("lxml", ("lxml",), "ускоренный разбор справки"),
)

# --- по желанию: тяжёлое, для поиска по справке и видео -------------------
OPTIONAL_PACKAGES: tuple[PackageSpec, ...] = (
    PackageSpec("chromadb", ("chromadb",),
                "векторный поиск по справке (пункт 6)", heavy=True),
    PackageSpec("sentence-transformers", ("sentence_transformers",),
                "смысловой поиск (пункт 6)", heavy=True),
    PackageSpec("faster-whisper", ("faster_whisper",),
                "разбор видео в текст", heavy=True),
    PackageSpec("PyMuPDF", ("fitz",), "разбор PDF справки", heavy=True),
    PackageSpec("ollama", ("ollama",), "локальный ИИ без ключа", heavy=True),
)


def module_available(module: str) -> bool:
    """Есть ли модуль. Не падает: любой странный случай — считаем «нет»."""
    try:
        # Сбрасываем кэш: сразу после pip install файлы уже на диске, но Python
        # ещё помнит старый список папок и говорит «нет пакета».
        importlib.invalidate_caches()
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError, TypeError):
        return False


def package_ok(spec: PackageSpec) -> bool:
    """Работает ли пакет: достаточно одного живого модуля из списка."""
    return any(module_available(module) for module in spec.modules)


def missing(base: bool = True, optional: bool = False) -> list[PackageSpec]:
    """Чего не хватает. По умолчанию — только обязательный набор."""
    wanted: list[PackageSpec] = []
    if base:
        wanted.extend(BASE_PACKAGES)
    if optional:
        wanted.extend(OPTIONAL_PACKAGES)
    return [spec for spec in wanted if not package_ok(spec)]


def state(base: bool = True, optional: bool = True) -> list[tuple[PackageSpec, bool]]:
    """Пакет + стоит ли он. Для отчётов и проверки компьютера."""
    wanted: list[PackageSpec] = []
    if base:
        wanted.extend(BASE_PACKAGES)
    if optional:
        wanted.extend(OPTIONAL_PACKAGES)
    return [(spec, package_ok(spec)) for spec in wanted]


def missing_names(base: bool = True, optional: bool = False) -> list[str]:
    return [spec.package for spec in missing(base=base, optional=optional)]


def summary_lines(python: str | None = None) -> list[str]:
    """Короткие строки для журнала окна: чего не хватает и как это поставить."""
    interpreter = python or sys.executable
    lack = missing(base=True)
    lines = [f"Python:  {interpreter}"]
    if lack:
        lines.append("Не хватает библиотек: " + ", ".join(s.package for s in lack))
        for spec in lack:
            lines.append(f"    • {spec.package} — {spec.purpose}")
        lines.append("Поставить: кнопка «Установить недостающее» здесь или "
                      "пункт 43 меню.")
    else:
        lines.append("Библиотеки для работы с PowerMill на месте.")
    return lines


def pip_command(packages: list[PackageSpec] | list[str],
                python: str | Path | None = None) -> list[str]:
    """Команда установки. Тем же интерпретатором, что запустил программу."""
    names = [item.package if isinstance(item, PackageSpec) else item
             for item in packages]
    return [str(python or sys.executable), "-m", "pip", "install",
            "--upgrade", "--upgrade-strategy", "only-if-needed", *names]


def install(packages: list[PackageSpec] | list[str],
            python: str | Path | None = None,
            log=None, timeout: int = 3600) -> tuple[bool, str]:
    """Ставит пакеты и рассказывает, что происходит, — построчно в `log`.

    Возвращает (успех, короткий итог). Не падает: любые проблемы возвращаются
    текстом, чтобы окно показало их в журнале, а батник — на экране.
    """
    say = log or (lambda text: None)
    names = [item.package if isinstance(item, PackageSpec) else item
             for item in packages]
    if not names:
        return True, "ставить нечего — всё на месте"

    command = pip_command(packages, python)
    say("Ставлю библиотеки: " + ", ".join(names))
    say("(это может занять несколько минут; интернет нужен только сейчас)")
    say("$ " + " ".join(command))
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace", bufsize=1)
    except OSError as error:
        return False, f"не удалось запустить pip: {error}"

    assert process.stdout is not None
    tail: list[str] = []
    for line in process.stdout:
        text = line.rstrip("\n").rstrip("\r")
        if not text:
            continue
        tail.append(text)
        if len(tail) > 400:
            tail = tail[-200:]
        say(text)
    code = process.wait()
    if code == 0:
        return True, "установлено: " + ", ".join(names)
    last = [line for line in tail if line.strip()][-6:]
    return False, "pip закончился с кодом %d: %s" % (code, " | ".join(last))


def report_lines(python: str | Path | None = None,
                 installed: list[str] | None = None) -> list[str]:
    """Отчёт «что было / что поставили / что теперь» — его можно прислать в чат."""
    import time

    interpreter = str(python or sys.executable)
    lines = [
        "=" * 60,
        "  БИБЛИОТЕКИ PowerMill AI",
        "=" * 60,
        f"  Проверено: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Python:    {interpreter}",
        "",
    ]
    if installed:
        lines.append("Поставлено сейчас: " + ", ".join(installed))
        lines.append("")
    for title, base, optional in (("Обязательные", True, False),
                                  ("По желанию", False, True)):
        lines.append(f"{title}:")
        for spec, ok in state(base=base, optional=optional):
            # У обязательных отсутствие — это ошибка (✘), у «по желанию» —
            # просто пометка (•): иначе непонятно, что мешает работе.
            if ok:
                mark = "✔"
            else:
                mark = "•" if spec.heavy else "✘"
            lines.append(f"  {mark} {spec.package} — {spec.purpose}")
        lines.append("")

    lack = missing(base=True)
    if lack:
        lines.append("ИТОГ: не хватает обязательного — " +
                     ", ".join(spec.package for spec in lack))
        lines.append("  Поставить можно так:")
        lines.append("    • окно приложения -> кнопка «Установить недостающее»;")
        lines.append("    • меню start_menu.bat -> пункт 43;")
        lines.append("    • или install.bat (он ставит это вместе с приложением).")
    else:
        lines.append("ИТОГ: обязательные библиотеки на месте.")
    heavy_lack = missing(base=False, optional=True)
    if heavy_lack:
        lines.append("По желанию нет: " +
                     ", ".join(spec.package for spec in heavy_lack))
        lines.append("  (пункт 43 с ключом --all ставит и их — это долго и много)")
    return lines


def save_report(lines: list[str] | None = None,
                python: str | Path | None = None,
                installed: list[str] | None = None) -> Path:
    """Пишет отчёт на диск и отдаёт путь."""
    text = lines if lines is not None else report_lines(python, installed)
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text("\n".join(text) + "\n", encoding="utf-8")
    except OSError:
        pass
    return REPORT_FILE

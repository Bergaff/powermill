"""
Подготовка плагина PowerMill (шаг 2.2 плана) — без Visual Studio.

Что известно из официальной документации Autodesk
-------------------------------------------------
* Плагины PowerMill входят в поставку (с 2012 R2) и лежат в установке в папке
  `<установка>\\file\\plugins`, а в ней четыре папки:
  **Documentation** (как писать плагин на C#/VB), **Framework** (готовый каркас
  для связи с PowerMill), **Installers**, **Solutions** (исходники примеров).
* Плагин — это .NET-сборка, которую PowerMill находит через COM-регистрацию:
  `regasm.exe <ваш.dll> /register /codebase`.
* Для доступа к функциям PowerMill нужна библиотека типов, полученная из
  `pmill.exe` утилитой `tlbimp.exe` (свежая версия обычно уже лежит в поставке).
* Сборку .NET можно делать без Visual Studio: csc.exe входит в состав
  .NET Framework на любой Windows
  (`C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe`).

Что делает этот модуль
----------------------
Ничего не устанавливает. Он:
1. находит папку `file\\plugins` и показывает, что в ней есть;
2. копирует Framework и Solutions в `E:\\powermill-ai\\plugin\\из_установки`
   (чтобы работать с настоящим каркасом, а не с догадками);
3. вытаскивает из примеров **факты о каркасе**: какие классы объявлены, какие
   интерфейсы реализуются, какие GUID используются, какие using-и;
4. проверяет наличие csc.exe / regasm.exe / tlbimp.exe / dotnet;
5. пишет `plugin\\build.bat` и `plugin\\register.bat` с найденными путями
   и `plugin\\КАК_СОБРАТЬ.txt`.

По этим фактам пишется код плагина — уже под твою версию PowerMill, а не
«в общем виде».
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from config import OUTPUT_DIR

PLUGIN_ROOT = OUTPUT_DIR.parent / "plugin"
COPY_DIR = PLUGIN_ROOT / "из_установки"
REPORT_FILE = OUTPUT_DIR / "plugin_report.txt"

PLUGIN_SUBDIRS = ("Documentation", "Framework", "Installers", "Solutions")
SOURCE_EXTS = (".cs", ".vb", ".sln", ".csproj", ".vbproj", ".dll", ".chm", ".pdf")

# Где Windows держит инструменты сборки .NET
SDK_TOOLS = {
    "csc.exe": (
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    ),
    "regasm.exe": (
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\regasm.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\regasm.exe",
    ),
    "tlbimp.exe": (
        r"C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\tlbimp.exe",
        r"C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8.1 Tools\tlbimp.exe",
    ),
}

CLASS_RE = re.compile(
    r"^\s*(?:\[.*?\]\s*)*public\s+(?:sealed\s+|abstract\s+|partial\s+)*"
    r"class\s+([A-Za-z_]\w*)\s*(?::\s*([^{]+))?", re.M)
GUID_RE = re.compile(r"Guid\(\s*\"([0-9A-Fa-f\-]{36})\"")
USING_RE = re.compile(r"^\s*using\s+([\w\.]+)\s*;", re.M)
INTERFACE_RE = re.compile(
    r"^\s*(?:\[.*?\]\s*)*public\s+interface\s+([A-Za-z_]\w*)", re.M)


# --------------------------------------------------------------------------
# Поиск
# --------------------------------------------------------------------------
def plugin_folder(install_dir: Path) -> Path | None:
    """Папка file\\plugins внутри установки PowerMill."""
    for relative in ("file/plugins", "lib/plugins", "plugins"):
        candidate = install_dir / relative
        if candidate.exists():
            return candidate
    return None


def find_plugin_dirs(extra: list[str] | None = None) -> list[Path]:
    """Все найденные папки плагинов (по установкам PowerMill на машине)."""
    from src.power_mill_link import find_install_dirs

    found: list[Path] = []
    for raw in list(extra or []):
        path = Path(raw)
        if path.name.lower() == "plugins" and path.exists():
            found.append(path)
    for install in find_install_dirs(extra):
        folder = plugin_folder(install)
        if folder and folder not in found:
            found.append(folder)
    return found


def sdk_tools() -> dict[str, str | None]:
    """Что из инструментов сборки есть на машине."""
    result: dict[str, str | None] = {}
    for name, paths in SDK_TOOLS.items():
        found = next((p for p in paths if Path(p).exists()), None)
        result[name] = found
    # полный .NET SDK, если установлен
    try:
        import subprocess

        out = subprocess.run(["dotnet", "--version"], capture_output=True,
                             text=True, timeout=20)
        result["dotnet sdk"] = (out.stdout or "").strip() if out.returncode == 0 else None
    except Exception:  # noqa: BLE001
        result["dotnet sdk"] = None
    return result


def read_sources(folder: Path, limit: int = 4000) -> list[Path]:
    """Исходники примеров плагинов внутри папки установки."""
    files: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in (".cs", ".vb", ".csproj", ".vbproj", ".sln"):
            files.append(path)
        if len(files) >= limit:
            break
    return files


def facts_from_sources(files: list[Path]) -> dict:
    """Вытаскивает из примеров то, что нужно для своего плагина."""
    classes: list[str] = []
    interfaces: list[str] = []
    guids: list[str] = []
    usings: set[str] = set()

    for path in files:
        if path.suffix.lower() not in (".cs", ".vb"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in CLASS_RE.finditer(text):
            base = (match.group(2) or "").replace("\n", " ").strip()
            classes.append(f"{match.group(1)} : {base}" if base else match.group(1))
        interfaces += INTERFACE_RE.findall(text)
        guids += GUID_RE.findall(text)
        usings.update(USING_RE.findall(text))

    return {
        "classes": classes[:60],
        "interfaces": sorted(set(interfaces))[:30],
        "guids": sorted(set(guids))[:20],
        "usings": sorted(usings)[:60],
    }


# --------------------------------------------------------------------------
# Копирование и генерация скриптов сборки
# --------------------------------------------------------------------------
def copy_install_files(plugin_dir: Path, copy_dir: Path = COPY_DIR) -> dict[str, int]:
    """Копирует Framework/Solutions/Documentation к нам — чтобы работать с ними."""
    stats: dict[str, int] = {}
    for sub in PLUGIN_SUBDIRS:
        source = plugin_dir / sub
        if not source.exists():
            stats[sub] = 0
            continue
        target = copy_dir / sub
        copied = 0
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SOURCE_EXTS and "Documentation" not in sub:
                continue
            relative = path.relative_to(source)
            destination = target / relative
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copy2(path, destination)
                    copied += 1
            except OSError:
                continue
        stats[sub] = copied
    return stats


def write_build_scripts(plugin_dir: Path, tools: dict[str, str | None],
                        framework_dll: str) -> list[Path]:
    """Создаёт build.bat и register.bat с найденными путями."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    csc = tools.get("csc.exe") or r"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    regasm = tools.get("regasm.exe") or r"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\regasm.exe"

    build = f"""@echo off
chcp 65001 >nul
title PowerMill AI - сборка плагина
cd /d "%~dp0"
echo =========================================================
echo   СБОРКА ПЛАГИНА PowerMill AI
echo =========================================================
echo.

set "CSC={csc}"
set "REGASM={regasm}"
set "FRAMEWORK={framework_dll}"

if not exist "%CSC%" goto no_csc
if not exist "PowerMillAI.cs" goto no_source
if "%FRAMEWORK%"=="" goto no_framework

echo Компилирую PowerMillAI.dll ...
"%CSC%" /target:library /out:PowerMillAI.dll /platform:x64 ^
  /reference:"%FRAMEWORK%" /reference:System.dll /reference:System.Windows.Forms.dll ^
  PowerMillAI.cs
if errorlevel 1 goto build_failed

echo.
echo [OK] Собрано: %CD%\\PowerMillAI.dll
echo.
echo Дальше запусти register.bat (от имени администратора).
echo.
pause
exit /b 0

:no_csc
echo [!] Не найден csc.exe по пути:
echo     %CSC%
echo     Установи .NET Framework 4.x или Visual Studio Build Tools.
pause
exit /b 1

:no_source
echo [!] Нет файла PowerMillAI.cs рядом с этим батником.
pause
exit /b 1

:no_framework
echo [!] Не указан путь к сборке каркаса (Framework).
echo     Запусти пункт 25 меню заново: он найдёт её и подставит сюда.
pause
exit /b 1

:build_failed
echo.
echo [!] Сборка не удалась. Скопируй текст ошибки и пришли в чат ассистента.
pause
exit /b 1
"""
    register = f"""@echo off
chcp 65001 >nul
title PowerMill AI - регистрация плагина в PowerMill
cd /d "%~dp0"
echo =========================================================
echo   РЕГИСТРАЦИЯ ПЛАГИНА В PowerMill
echo   Нужны права администратора!
echo =========================================================
echo.

set "REGASM={regasm}"
if not exist "%REGASM%" goto no_regasm
if not exist "PowerMillAI.dll" goto no_dll

"%REGASM%" PowerMillAI.dll /register /codebase
if errorlevel 1 goto failed

echo.
echo [OK] Плагин зарегистрирован.
echo   Открой PowerMill: вкладка Инструменты (Tools) -^> Плагины
echo   В списке должен появиться «PowerMill AI».
echo.
pause
exit /b 0

:no_regasm
echo [!] Не найден regasm.exe: %REGASM%
pause
exit /b 1

:no_dll
echo [!] Сначала собери плагин: build.bat
pause
exit /b 1

:failed
echo.
echo [!] Регистрация не удалась. Проверь права администратора
echo     и пришли текст ошибки в чат.
pause
exit /b 1
"""
    for name, text in (("build.bat", build), ("register.bat", register)):
        path = plugin_dir / name
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        written.append(path)
    return written


# --------------------------------------------------------------------------
# Отчёт
# --------------------------------------------------------------------------
def report(verbose: bool = True) -> tuple[str, bool]:
    """Собирает сведения о плагинах PowerMill. Возвращает (текст, есть ли что-то)."""
    folders = find_plugin_dirs()
    tools = sdk_tools()
    lines = ["=" * 62,
             "  ПОДГОТОВКА ПЛАГИНА PowerMill",
             "=" * 62, ""]

    if not folders:
        lines.append("Папка file\\plugins в установках PowerMill не найдена.")
        lines.append("Что это значит: плагины в поставке есть не всегда.")
        lines.append("Тогда путь к плагину: поставить Visual Studio (Community, бесплатно)")
        lines.append("и собрать плагин по документации Autodesk, либо остаться")
        lines.append("на маршруте «макросы + снимок проекта» (пункты 23–24).")
        return "\n".join(lines), False

    total_facts: dict = {}
    framework_dll = ""
    for folder in folders:
        lines.append(f"Папка плагинов: {folder}")
        for sub in PLUGIN_SUBDIRS:
            target = folder / sub
            if not target.exists():
                lines.append(f"  {sub}: нет")
                continue
            files = [p for p in target.rglob("*") if p.is_file()]
            lines.append(f"  {sub}: {len(files)} файлов")
            for path in files[:4]:
                lines.append(f"      {path.name}")
            if len(files) > 4:
                lines.append(f"      … ещё {len(files) - 4}")

        copied = copy_install_files(folder)
        if any(copied.values()):
            lines.append("  Скопировано к нам:")
            for sub, count in copied.items():
                if count:
                    lines.append(f"      {sub}: {count} -> {COPY_DIR / sub}")

        sources = read_sources(folder)
        if sources:
            facts = facts_from_sources(sources)
            total_facts = facts
            lines.append(f"  Факты о каркасе (из {len(sources)} исходников):")
            if facts["classes"]:
                lines.append("    классы: " + "; ".join(facts["classes"][:8]))
            if facts["interfaces"]:
                lines.append("    интерфейсы: " + ", ".join(facts["interfaces"][:8]))
            if facts["guids"]:
                lines.append("    примеры GUID: " + ", ".join(facts["guids"][:3]))
            if facts["usings"]:
                lines.append("    using: " + ", ".join(facts["usings"][:10]))

        # сборка каркаса (Framework) — её и подключим при сборке
        for candidate in (folder / "Framework").rglob("*.dll"):
            framework_dll = str(candidate)
            break
        if not framework_dll:
            for candidate in (folder / "Solutions").rglob("*.dll"):
                framework_dll = str(candidate)
                break
        if framework_dll:
            lines.append(f"  Каркас для ссылки: {framework_dll}")

    lines += ["", "Инструменты сборки на этой машине:"]
    for name, path in tools.items():
        lines.append(f"  {'[есть]' if path else '[НЕТ] '} {name}: {path or '—'}")
    missing = [n for n, p in tools.items() if not p]
    if "csc.exe" in missing:
        lines.append("  csc.exe входит в .NET Framework — обычно уже есть в Windows.")
    if "tlbimp.exe" in missing:
        lines.append("  tlbimp.exe нужен только если придётся строить библиотеку "
                     "типов из pmill.exe (часто она уже есть в поставке).")

    lines += ["", "=" * 62, "  ЧТО ДАЛЬШЕ", "=" * 62]
    ready = bool(tools.get("csc.exe") or tools.get("dotnet sdk"))
    if total_facts.get("classes"):
        lines.append("  Каркас и примеры найдены — по ним пишется код плагина")
        lines.append("  под твою версию PowerMill (это следующий шаг, код уже готовлю).")
    else:
        lines.append("  Исходников примеров нет: плагин придётся писать по документации")
        lines.append("  Autodesk (папка Documentation), каркас — из папки Framework.")
    lines.append(f"  Сборка возможна без Visual Studio: {'да' if ready else 'нужно поставить .NET'}")
    lines.append(f"  Рабочая папка плагина: {PLUGIN_ROOT}")
    return "\n".join(lines), True


def main() -> int:
    text, found = report()
    print(text)
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(text, encoding="utf-8")
        print(f"\n📝 Отчёт: {REPORT_FILE}")
        print("   Пришли его в чат — я подгоню код плагина под твою установку.")
    except OSError:
        pass

    # заготовка исходника: заполняется, когда известен каркас
    plugin_dir = PLUGIN_ROOT
    plugin_dir.mkdir(parents=True, exist_ok=True)
    readme = plugin_dir / "КАК_СОБРАТЬ.txt"
    readme.write_text(
        "Плагин PowerMill AI — рабочая папка\n"
        "===================================\n\n"
        "1. Запусти пункт 25 меню (подготовка плагина) — он найдёт каркас\n"
        "   PowerMill (папка file\\plugins\\Framework) и примеры (Solutions).\n"
        "2. Пришли в чат отчёт output\\plugin_report.txt.\n"
        "3. Получишь PowerMillAI.cs — код плагина под твою версию PowerMill.\n"
        "   Положи его в эту папку и запусти build.bat (сборка без Visual Studio).\n"
        "4. Затем register.bat от имени администратора — плагин появится\n"
        "   в PowerMill: вкладка Инструменты (Tools) -> Плагины.\n\n"
        "Пока плагин не собран, всё остальное работает и без него:\n"
        "  пункт 24 — снимок проекта, /macro в чате, режимы резания.\n",
        encoding="utf-8")

    if found:
        print(f"\nПапка плагина подготовлена: {plugin_dir}")
        print(f"  {readme.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

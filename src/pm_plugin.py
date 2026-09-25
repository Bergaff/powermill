"""
Плагин-окно «PowerMill AI» внутри PowerMill (шаг 2.3б, пункт 38).

Зачем плагин, если уже есть макросы
-----------------------------------
Макросы — это «руки»: они умеют всё то же, что человек за клавиатурой, и уже
работают (пункты 30–37). Плагин — это «лицо»: собственное окно-панель внутри
PowerMill, кнопки без ухода в консоль, журнал того, что делает ассистент.
Мозг в обоих случаях один и тот же — наш Python (те же сценарии пунктов 3, 31,
33, 35, 36, 37), поэтому плагин ничего не «переписывает», а показывает.

Что здесь есть
--------------
1. **Сборка исходника на C#** — по фактам каркаса Autodesk
   (`Delcam.Plugins.Framework`, класс-наследник `PluginFrameworkWithPanes`,
   `register_pane(new PaneDefinition(pane, …))`, атрибуты `[Guid]`,
   `[ClassInterface(ClassInterfaceType.None)]`, `[ComVisible(true)]`).
   UI — без XAML (панель собирается кодом), поэтому для сборки хватает
   `csc.exe` из .NET Framework: Visual Studio не нужна.
2. **Команды сборки и регистрации** — `csc.exe` + `regasm.exe /register /codebase`
   + запись компонентной категории плагинов PowerMill в реестр (без неё PowerMill
   плагин просто не увидит).
3. **Честная проверка окружения** — чего не хватает (компилятор, каркас,
   Python проекта), чтобы не обещать сборку, которой не будет.

Что модуль НЕ делает: он не компилирует и не лезет в реестр. Это делает
`scripts\\build_plugin.bat` на твоём компьютере и говорит, что получилось.
И ни одного обещания «плагин заработает»: проверить это можно только у тебя.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from config import DATA_ROOT, OUTPUT_DIR

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = DATA_ROOT / "plugin"
PROJECT_DIR = PLUGIN_ROOT / "PowerMillAI"
COPY_DIR = PLUGIN_ROOT / "из_установки"          # сюда пункт 25 копирует каркас
SOURCE_NAME = "PowerMillAI.cs"
DLL_NAME = "PowerMillAI.dll"
CLASS_NAME = "PowerMillAI"
NAMESPACE = "PowerMillAi"
PANE_TITLE = "PowerMill AI"
ASSEMBLY_NAME = "PowerMillAI"

# GUID плагина: у каждого плагина должен быть свой и постоянный. Этот — наш;
# его же пишем в реестр вместе с компонентной категорией плагинов PowerMill.
PLUGIN_GUID = "6E5B2A1C-1D2E-4F30-9A7B-0C4D5E6F7A81"

# Компонентная категория плагинов PowerMill (из официального примера Autodesk
# powermill-api-examples — там же и вторая, из старого руководства по плагинам).
PLUGIN_CATEGORY_GUIDS = (
    "{311b0135-1826-4a8c-98de-f313289f815e}",
    "{6e90c6bf-ebe9-427f-bffb-e883815ea72e}",
)

FRAMEWORK_DLL_NAMES = (
    "Delcam.Plugins.Framework.dll",
    "Delcam.Plugins.Framework.BaseClasses.dll",
)
EXTRA_DLL_NAMES = (
    "PowerMILL.dll",
    "pmill.dll",
    "Delcam.ProductInterface.PowerMILL.dll",
)

DEFAULT_PM_VERSION = "2026.0"
REPORT_FILE = OUTPUT_DIR / "pm_plugin_build_report.txt"


# --------------------------------------------------------------------------
# Кнопки панели: те же сценарии, что и на ленте (пункт 34)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PluginButton:
    """Кнопка панели.

    * `bat` пустой — сценарий идёт прямо в панель (вопросов не задаёт);
    * `bat` задан — сценарий спрашивает технолога, поэтому запускаем его
      отдельным окном, как двойным щелчком (иначе он будет ждать ввода,
      которого в панели нет).
    """

    label: str
    module: str
    hint: str = ""
    arguments: str = ""
    bat: str = ""


PANE_BUTTONS: tuple[PluginButton, ...] = (
    PluginButton("Режимы резания", "src.cutting", "Калькулятор S/F (пункт 3)",
                 bat="start_cutting.bat"),
    PluginButton("Фреза в проект", "scripts.probe_tool", "Создать фрезу (пункт 33)",
                 bat="scripts\\probe_tool.bat"),
    PluginButton("Черновая операция", "scripts.make_operation",
                 "Инструмент + заготовка + траектория (пункт 31)",
                 bat="scripts\\make_operation.bat"),
    PluginButton("Проверки (3.4)", "scripts.check_toolpaths",
                 "Зарезы и столкновения (пункт 35)",
                 bat="scripts\\check_toolpaths.bat"),
    PluginButton("NC-программа (3.5)", "scripts.make_nc", "Вывод NC (пункт 36)",
                 bat="scripts\\make_nc.bat"),
    PluginButton("СДЕЛАЙ (3.6)", "scripts.make_flow",
                 "План → выполнение → проверки → NC (пункт 37)",
                 bat="scripts\\make_flow.bat"),
    PluginButton("Снимок проекта", "scripts.load_project",
                 "Ассистент узнаёт имена объектов проекта"),
    PluginButton("Отчёты", "scripts.show_reports", "Открыть отчёты в блокноте",
                 bat="scripts\\show_reports.bat"),
    PluginButton("Чат в браузере", "scripts.chat_ui", "Интерфейс пункта 32",
                 arguments="--open"),
)


@dataclass
class PluginSpec:
    """Что за плагин собираем."""

    plugin_name: str = PANE_TITLE
    pm_version: str = DEFAULT_PM_VERSION
    ui: str = "wpf"                        # "wpf" (как в примерах) или "winforms"
    python_exe: Path | None = None
    project_dir: Path = PROJECT_ROOT
    buttons: tuple[PluginButton, ...] = PANE_BUTTONS
    output_dir: Path = PROJECT_DIR
    guid: str = PLUGIN_GUID


def python_exe(project_dir: Path | str = PROJECT_ROOT) -> Path | None:
    """Python проекта: тот же, что у батников (.venv → venv → python из PATH)."""
    root = Path(project_dir)
    for candidate in (root / ".venv" / "Scripts" / "python.exe",
                      root / "venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def source_path(output_dir: Path | str = PROJECT_DIR) -> Path:
    return Path(output_dir) / SOURCE_NAME


def dll_path(output_dir: Path | str = PROJECT_DIR) -> Path:
    return Path(output_dir) / DLL_NAME


# --------------------------------------------------------------------------
# Исходник на C#
# --------------------------------------------------------------------------
def cs_str(text: str) -> str:
    """Строка для C#-литерала (кавычки, слэши, переводы строк)."""
    return (text.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\r", "\\r").replace("\n", "\\n"))


def _version_literal(version: str) -> str:
    parts = [part for part in str(version).replace(",", ".").split(".") if part.strip()]
    numbers = [str(int(part)) if part.strip().isdigit() else "0" for part in parts[:2]]
    while len(numbers) < 2:
        numbers.append("0")
    return ", ".join(numbers)


def _button_calls(spec: PluginSpec, indent: str) -> list[str]:
    lines: list[str] = []
    for button in spec.buttons:
        lines.append(
            f'{indent}AddButton(panel, "{cs_str(button.label)}", '
            f'"{cs_str(button.module)}", "{cs_str(button.arguments)}", '
            f'"{cs_str(button.bat)}");'
        )
    return lines


WPF_HEADER = """// ============================================================
//  PowerMill AI — панель-плагин внутри PowerMill (пункт 38, шаг 2.3б)
//  Файл СОБРАН скриптом scripts\\build_plugin.bat — правки затрутся.
//  Собрано: @@WHEN@@
//
//  Что это: окно-панель с кнопками сценариев и журналом.
//  Что это НЕ делает: не заменяет Python-мозг ассистента — кнопки запускают
//  те же самые сценарии (пункты 3, 31, 33, 35, 36, 37).
// ============================================================
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using Delcam.Plugins.Framework;

namespace @@NAMESPACE@@
{
    // Атрибуты COM: после `regasm PowerMillAI.dll /register /codebase` PowerMill
    // находит плагин по этому GUID.
    [Guid("@@GUID@@")]
    [ClassInterface(ClassInterfaceType.None)]
    [ComVisible(true)]
    public class @@CLASS@@ : PluginFrameworkWithPanes
    {
        private AiPane m_pane;

        public override string PluginName { get { return "@@NAME@@"; } }
        public override string PluginAuthor { get { return "PowerMill AI"; } }
        public override string PluginDescription
        {
            get { return "Ассистент технолога: режимы, фреза, черновая, проверки, NC"; }
        }
        public override string PluginIconPath { get { return null; } }
        public override Version PluginVersion { get { return new Version(1, 0, 0); } }
        public override Version PowerMILLVersion { get { return new Version(@@PMVERSION@@); } }
        public override bool PluginHasOptions { get { return false; } }
        public override string PluginAssemblyName { get { return "@@ASSEMBLY@@"; } }
        public override Guid PluginGuid { get { return new Guid("@@GUID@@"); } }

        protected override void register_panes()
        {
            m_pane = new AiPane();
            register_pane(new PaneDefinition(m_pane, 900, 375, "@@NAME@@", null));
        }
    }

    // Панель: кнопки сценариев + журнал вывода
    public class AiPane : UserControl
    {
        private const string PYTHON = "@@PYTHON@@";
        private const string PROJECT = "@@PROJECT@@";
        private readonly TextBox m_log;
        private Process m_running;

        public AiPane()
        {
            m_log = new TextBox();
            m_log.IsReadOnly = true;
            m_log.AcceptsReturn = true;
            m_log.TextWrapping = TextWrapping.NoWrap;
            m_log.VerticalScrollBarVisibility = ScrollBarVisibility.Auto;
            m_log.FontFamily = new System.Windows.Media.FontFamily("Consolas");
            m_log.FontSize = 12;

            var panel = new WrapPanel();
@@BUTTONS@@
            var root = new DockPanel();
            DockPanel.SetDock(panel, Dock.Top);
            root.Children.Add(panel);
            root.Children.Add(m_log);
            this.Content = root;

            Append("PowerMill AI: панель готова. Кнопки со значком «окно» спрашивают своё в отдельном окне.");
            Append("Python: " + PYTHON);
            Append("Проект: " + PROJECT);
        }

        private void AddButton(Panel panel, string title, string module, string arguments, string bat)
        {
            var button = new Button();
            button.Content = (bat.Length > 0) ? (title + " — окно") : title;
            button.Margin = new Thickness(2);
            button.Padding = new Thickness(8, 4, 8, 4);
            button.ToolTip = (bat.Length > 0) ? (bat + " (откроется своё окно)") : (module + " " + arguments);
            button.Click += delegate { if (bat.Length > 0) { RunWindow(title, bat); } else { RunInline(title, module, arguments); } };
            panel.Children.Add(button);
        }

        private void Append(string text)
        {
            Dispatcher.Invoke((Action)delegate
            {
                m_log.AppendText(text + "\\r\\n");
                m_log.ScrollToEnd();
            });
        }

        private void RunInline(string title, string module, string arguments)
        {
            if (string.IsNullOrEmpty(PYTHON))
            {
                Append("(!) Python проекта не найден — запусти пункт 27 установки пакетов.");
                return;
            }
            Start(title, PYTHON, ("-m " + module + " " + arguments).Trim(), false);
        }

        private void RunWindow(string title, string bat)
        {
            string path = Path.Combine(PROJECT, bat);
            if (!File.Exists(path))
            {
                Append("(!) нет файла " + path + " — проверь, что репозиторий на месте.");
                return;
            }
            Start(title, path, "", true);
        }

        private void Start(string title, string file, string arguments, bool inWindow)
        {
            if (m_running != null && !m_running.HasExited)
            {
                Append("Сейчас уже идёт другой сценарий — дождись его конца.");
                return;
            }
            Append("");
            Append("=== " + title + " ===");
            try
            {
                var info = new ProcessStartInfo(file, arguments);
                info.WorkingDirectory = PROJECT;
                info.UseShellExecute = inWindow;
                if (!inWindow)
                {
                    info.RedirectStandardOutput = true;
                    info.RedirectStandardError = true;
                    info.CreateNoWindow = true;
                    info.StandardOutputEncoding = Encoding.UTF8;
                    info.StandardErrorEncoding = Encoding.UTF8;
                    info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                    info.EnvironmentVariables["APP_MODE"] = "eco";
                }
                m_running = new Process();
                m_running.StartInfo = info;
                if (!inWindow)
                {
                    m_running.EnableRaisingEvents = true;
                    m_running.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
                    {
                        if (e.Data != null) { Append(e.Data); }
                    };
                    m_running.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
                    {
                        if (e.Data != null) { Append("(!) " + e.Data); }
                    };
                    m_running.Exited += delegate { Append("=== " + title + ": закончилось ==="); };
                }
                else
                {
                    Append("Открыл отдельное окно — отвечай на вопросы там.");
                }
                m_running.Start();
                if (!inWindow)
                {
                    m_running.BeginOutputReadLine();
                    m_running.BeginErrorReadLine();
                }
            }
            catch (Exception error)
            {
                Append("(!) не удалось запустить: " + error.Message);
            }
        }
    }
}
"""

WINFORMS_UI = """    // Панель: кнопки сценариев + журнал вывода (WinForms)
    public class AiPane : System.Windows.Forms.UserControl
    {
        private const string PYTHON = "@@PYTHON@@";
        private const string PROJECT = "@@PROJECT@@";
        private readonly System.Windows.Forms.TextBox m_log;
        private Process m_running;

        public AiPane()
        {
            m_log = new System.Windows.Forms.TextBox();
            m_log.Multiline = true;
            m_log.ReadOnly = true;
            m_log.ScrollBars = System.Windows.Forms.ScrollBars.Both;
            m_log.WordWrap = false;
            m_log.Dock = System.Windows.Forms.DockStyle.Fill;
            m_log.Font = new System.Drawing.Font("Consolas", 9f);

            var panel = new System.Windows.Forms.FlowLayoutPanel();
            panel.Dock = System.Windows.Forms.DockStyle.Top;
            panel.AutoSize = true;
            panel.WrapContents = true;
@@BUTTONS@@
            this.Controls.Add(m_log);
            this.Controls.Add(panel);

            Append("PowerMill AI: панель готова.");
            Append("Python: " + PYTHON);
            Append("Проект: " + PROJECT);
        }

        private void AddButton(System.Windows.Forms.FlowLayoutPanel panel, string title,
                               string module, string arguments, string bat)
        {
            var button = new System.Windows.Forms.Button();
            button.Text = (bat.Length > 0) ? (title + " — окно") : title;
            button.AutoSize = true;
            button.Margin = new System.Windows.Forms.Padding(2);
            button.Click += delegate { if (bat.Length > 0) { RunWindow(title, bat); } else { RunInline(title, module, arguments); } };
            panel.Controls.Add(button);
        }

        private void Append(string text)
        {
            if (this.InvokeRequired)
            {
                this.Invoke((Action)delegate { Append(text); });
                return;
            }
            m_log.AppendText(text + "\\r\\n");
        }

        private void RunInline(string title, string module, string arguments)
        {
            if (string.IsNullOrEmpty(PYTHON))
            {
                Append("(!) Python проекта не найден — запусти пункт 27.");
                return;
            }
            Start(title, PYTHON, ("-m " + module + " " + arguments).Trim(), false);
        }

        private void RunWindow(string title, string bat)
        {
            string path = Path.Combine(PROJECT, bat);
            if (!File.Exists(path))
            {
                Append("(!) нет файла " + path);
                return;
            }
            Start(title, path, "", true);
        }

        private void Start(string title, string file, string arguments, bool inWindow)
        {
            if (m_running != null && !m_running.HasExited)
            {
                Append("Сейчас уже идёт другой сценарий — дождись его конца.");
                return;
            }
            Append("");
            Append("=== " + title + " ===");
            try
            {
                var info = new ProcessStartInfo(file, arguments);
                info.WorkingDirectory = PROJECT;
                info.UseShellExecute = inWindow;
                if (!inWindow)
                {
                    info.RedirectStandardOutput = true;
                    info.RedirectStandardError = true;
                    info.CreateNoWindow = true;
                    info.StandardOutputEncoding = Encoding.UTF8;
                    info.StandardErrorEncoding = Encoding.UTF8;
                    info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                    info.EnvironmentVariables["APP_MODE"] = "eco";
                }
                m_running = new Process();
                m_running.StartInfo = info;
                if (!inWindow)
                {
                    m_running.EnableRaisingEvents = true;
                    m_running.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
                    {
                        if (e.Data != null) { Append(e.Data); }
                    };
                    m_running.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
                    {
                        if (e.Data != null) { Append("(!) " + e.Data); }
                    };
                    m_running.Exited += delegate { Append("=== " + title + ": закончилось ==="); };
                }
                else
                {
                    Append("Открыл отдельное окно — отвечай на вопросы там.");
                }
                m_running.Start();
                if (!inWindow)
                {
                    m_running.BeginOutputReadLine();
                    m_running.BeginErrorReadLine();
                }
            }
            catch (Exception error)
            {
                Append("(!) не удалось запустить: " + error.Message);
            }
        }
    }
}
"""

WINFORMS_HEADER_TAIL = """using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Delcam.Plugins.Framework;

namespace @@NAMESPACE@@
{
    [Guid("@@GUID@@")]
    [ClassInterface(ClassInterfaceType.None)]
    [ComVisible(true)]
    public class @@CLASS@@ : PluginFrameworkWithPanes
    {
        private AiPane m_pane;

        public override string PluginName { get { return "@@NAME@@"; } }
        public override string PluginAuthor { get { return "PowerMill AI"; } }
        public override string PluginDescription
        {
            get { return "Ассистент технолога: режимы, фреза, черновая, проверки, NC"; }
        }
        public override string PluginIconPath { get { return null; } }
        public override Version PluginVersion { get { return new Version(1, 0, 0); } }
        public override Version PowerMILLVersion { get { return new Version(@@PMVERSION@@); } }
        public override bool PluginHasOptions { get { return false; } }
        public override string PluginAssemblyName { get { return "@@ASSEMBLY@@"; } }
        public override Guid PluginGuid { get { return new Guid("@@GUID@@"); } }

        protected override void register_panes()
        {
            m_pane = new AiPane();
            register_pane(new PaneDefinition(m_pane, 900, 375, "@@NAME@@", null));
        }
    }

"""


def build_source(spec: PluginSpec, when: str | None = None) -> str:
    """Собирает исходник плагина (ComVisible-класс + панель с кнопками)."""
    stamp = when or time.strftime("%d.%m.%Y %H:%M")
    buttons = _button_calls(spec, indent=" " * 12)
    if spec.ui == "winforms":
        template = (
            WPF_HEADER.split("using System;", 1)[0]
            + WINFORMS_HEADER_TAIL.replace("@@BUTTONS@@", "\n".join(buttons))
            + WINFORMS_UI.replace("@@BUTTONS@@", "\n".join(buttons))
        )
    else:
        template = WPF_HEADER.replace("@@BUTTONS@@", "\n".join(buttons))

    python = spec.python_exe or ""
    text = (template
            .replace("@@WHEN@@", stamp)
            .replace("@@NAMESPACE@@", NAMESPACE)
            .replace("@@CLASS@@", CLASS_NAME)
            .replace("@@ASSEMBLY@@", ASSEMBLY_NAME)
            .replace("@@NAME@@", cs_str(spec.plugin_name))
            .replace("@@GUID@@", spec.guid)
            .replace("@@PMVERSION@@", _version_literal(spec.pm_version))
            .replace("@@PYTHON@@", cs_str(str(python).replace("/", "\\")))
            .replace("@@PROJECT@@", cs_str(str(spec.project_dir).replace("/", "\\"))))
    return text


def write_source(spec: PluginSpec) -> Path:
    """Пишет исходник: UTF-8 с BOM (чтобы csc верно прочитал русский текст)."""
    path = source_path(spec.output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\r\n".join(build_source(spec).splitlines()) + "\r\n"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    return path


# --------------------------------------------------------------------------
# Что нужно для сборки: компилятор, каркас, реестр
# --------------------------------------------------------------------------
def find_references(extra_dirs: list[Path] | None = None,
                    limit: int = 8) -> dict[str, list[str]]:
    """Ищет каркас плагинов и прочие сборки PowerMill для ссылок при сборке."""
    roots: list[Path] = [COPY_DIR] + list(extra_dirs or [])
    for candidate in (Path("C:/Program Files/Autodesk"), Path("E:/"),
                      Path("E:/powermill 2026")):
        if candidate.exists():
            roots.append(candidate)

    framework: list[str] = []
    extra: list[str] = []
    seen: set[str] = set()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        try:
            walker = root.rglob("*.dll")
            for path in walker:
                name = path.name
                if name in seen:
                    continue
                if name in FRAMEWORK_DLL_NAMES and len(framework) < limit:
                    framework.append(str(path))
                    seen.add(name)
                elif name in EXTRA_DLL_NAMES and len(extra) < limit:
                    extra.append(str(path))
                    seen.add(name)
                if len(framework) >= limit and len(extra) >= limit:
                    break
        except OSError:
            continue
    return {"framework": framework, "extra": extra}


def check_environment(tools: dict[str, str | None], references: dict[str, list[str]],
                      spec: PluginSpec) -> list[str]:
    """Что мешает сборке — списком, без обещаний «должно собраться»."""
    problems: list[str] = []
    if not tools.get("csc.exe"):
        problems.append("не найден csc.exe (компилятор .NET Framework) — без него "
                        "сборка невозможна; обычно лежит в "
                        "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\")
    if not tools.get("regasm.exe"):
        problems.append("не найден regasm.exe — без него PowerMill не увидит плагин")
    if not references.get("framework"):
        problems.append("не найден Delcam.Plugins.Framework.dll — сначала запусти "
                        "пункт 25 (он копирует каркас из поставки PowerMill)")
    if spec.python_exe is None:
        problems.append("не найден Python проекта (.venv\\Scripts\\python.exe) — "
                        "панель соберётся, но кнопки сценариев работать не будут; "
                        "запусти пункт 27")
    return problems


def compile_command(spec: PluginSpec, csc: str,
                    references: dict[str, list[str]]) -> list[str]:
    """Команда сборки DLL (csc без Visual Studio)."""
    refs = list(references.get("framework", [])) + list(references.get("extra", []))
    command = [csc, "/nologo", "/target:library", "/platform:anycpu",
               f"/out:{dll_path(spec.output_dir)}"]
    command += [f"/reference:{path}" for path in refs]
    command.append(str(source_path(spec.output_dir)))
    return command


def register_commands(spec: PluginSpec, regasm: str) -> list[list[str]]:
    """Регистрация в COM + компонентная категория плагинов PowerMill.

    Без записи в категорию PowerMill плагин не подхватывает — это самая частая
    причина «собрал, а в PowerMill ничего нет».
    """
    dll = dll_path(spec.output_dir)
    guid = "{" + spec.guid + "}"
    commands: list[list[str]] = [[regasm, str(dll), "/register", "/codebase"]]
    for category in PLUGIN_CATEGORY_GUIDS:
        key = rf"HKCR\CLSID\{guid}\Implemented Categories\{category}"
        for view in ("/reg:32", "/reg:64"):
            commands.append(["reg", "add", key, "/f", view])
    return commands


def unregister_commands(spec: PluginSpec, regasm: str) -> list[list[str]]:
    """Отмена регистрации (если плагин мешает)."""
    dll = dll_path(spec.output_dir)
    guid = "{" + spec.guid + "}"
    commands: list[list[str]] = [[regasm, str(dll), "/unregister"]]
    for category in PLUGIN_CATEGORY_GUIDS:
        key = rf"HKCR\CLSID\{guid}\Implemented Categories\{category}"
        for view in ("/reg:32", "/reg:64"):
            commands.append(["reg", "delete", key, "/f", view])
    return commands


def plan_lines(spec: PluginSpec, tools: dict[str, str | None],
               references: dict[str, list[str]]) -> list[str]:
    """Что будет сделано — до сборки."""
    lines = [
        f"  1. Исходник: {source_path(spec.output_dir)}",
        f"     класс {NAMESPACE}.{CLASS_NAME} (COM, GUID {spec.guid})",
        f"     UI: {'WPF (как в примерах Autodesk)' if spec.ui != 'winforms' else 'WinForms'}",
        f"     кнопок на панели: {len(spec.buttons)}",
    ]
    for button in spec.buttons:
        where = button.bat if button.bat else f"в панель: {button.module}"
        lines.append(f"        • {button.label} — {where}")
    lines.append(f"  2. Каркас для ссылок: {len(references.get('framework', []))} сборок"
                 + (f" ({Path(references['framework'][0]).name} …)"
                    if references.get("framework") else " — НЕ НАЙДЕН"))
    lines.append(f"  3. Компилятор: {tools.get('csc.exe') or '— не найден'}")
    lines.append(f"  4. Регистрация: {tools.get('regasm.exe') or '— не найден'} "
                 "/register /codebase + компонентная категория плагинов PowerMill")
    lines.append("  5. Python проекта для кнопок: "
                 + (str(spec.python_exe) if spec.python_exe else "— не найден"))
    return lines


def parse_build_output(text: str) -> tuple[list[str], list[str]]:
    """Ошибки и предупреждения компилятора из его вывода."""
    import re

    errors: list[str] = []
    warnings: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if "error CS" in stripped or ": error " in stripped:
            errors.append(stripped)
        elif "warning CS" in stripped or ": warning " in stripped:
            warnings.append(stripped)
    return errors, warnings


def format_result(problems: list[str], errors: list[str],
                  warnings: list[str], dll: Path | None) -> str:
    """Итог сборки — и обязательно то, что не проверено."""
    lines: list[str] = []
    if problems:
        lines.append("Сборка сейчас невозможна:")
        lines.extend(f"  ✘ {item}" for item in problems)
    if errors:
        lines.append(f"Ошибки компилятора ({len(errors)}):")
        lines.extend(f"  ✘ {item}" for item in errors[:20])
        if len(errors) > 20:
            lines.append(f"  … ещё {len(errors) - 20}")
    if warnings:
        lines.append(f"Предупреждения ({len(warnings)}):")
        lines.extend(f"  • {item}" for item in warnings[:10])
    if dll is not None:
        lines.append(f"Собрано: {dll}"
                     + (f" ({dll.stat().st_size} байт)" if dll.exists() else ""))
    if not lines:
        lines.append("Замечаний нет.")
    lines += [
        "",
        "Что НЕ проверено (честно):",
        "  • исходник не проверялся компилятором (в песочнице его нет) — если "
        "первая сборка покажет ошибки, пришли вывод, поправлю;",
        "  • что панель появится в PowerMill и что кнопки в ней работают — "
        "проверяется только у тебя, вживую;",
        "  • что версия каркаса совпадает с установленной версией PowerMill;",
        "  • что плагин не мешает другим плагинам (NCSIMUL, ViMill, Robot).",
    ]
    return "\n".join(lines)


def report(problems: list[str], plan: list[str], result: str,
           dll: Path | None) -> Path:
    """Отчёт о сборке — тем же порядком, что и остальные пункты."""
    lines = [
        "PowerMill AI — сборка плагина-панели (пункт 38, шаг 2.3б)",
        time.strftime("Собрано: %d.%m.%Y %H:%M"),
        "",
        "Что собираем:",
    ]
    lines += list(plan)
    lines += ["", "Проверка окружения:"]
    if problems:
        lines += [f"  ✘ {item}" for item in problems]
    else:
        lines.append("  ✔ всё на месте")
    lines += ["", "Результат:", result]
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT_FILE

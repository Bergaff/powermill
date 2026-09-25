"""
Окно приложения «PowerMill AI» (пункт 39).

Зачем окно, если есть консоль и браузер
---------------------------------------
Консоль — это «внутренности»: видно всё, но выглядит как отладка. Браузер
(пункт 32) — хорошо, но требует запущенного сервера. А это — **обычное окно
программы**: список действий, журнал, кнопки «Стоп», «Отчёты», «Проверка».
Двойной щелчок по ярлыку — и работает, ничего печатать не надо.

Что внутри
----------
* Список кнопок — **тот же самый**, что на ленте PowerMill (пункт 34) и в
  панели плагина (пункт 38): `src\\pm_buttons.py`. Ничего не дублируется.
* Сценарии с вопросами (черновая, проверки, NC, «СДЕЛАЙ») запускаются
  **отдельным окном** — им нужен ввод технолога.
* Сценарии без вопросов — прямо в журнал окна, построчно.
* Наши макросы («Ассистент», «Снимок проекта») окно выполняет **в PowerMill**
  через тот же живой COM, что и пункты 24/33 (см. `src\\pm_com.py`), и печатает
  ответ PowerMill: видно, принял ли он команду.

Модуль устроен так, что рисует окно только при запуске. Логика (какие кнопки,
что и чем запускать) — отдельные функции, поэтому её можно проверять тестами
без экрана.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from config import DATA_ROOT
from src import pm_buttons

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TITLE = "PowerMill AI — ассистент технолога"
WINDOW_SIZE = "1080x720"
LOG_LIMIT_LINES = 4000


# --------------------------------------------------------------------------
# Что и чем запускаем (чистая логика — её и проверяют тесты)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RunPlan:
    """Как запускать действие.

    * `kind="macro"` — выполнить макрос в PowerMill через COM (в потоке окна);
    * `kind="window"` — открыть сценарий отдельным окном (там вопросы);
    * `kind="inline"` — запустить в журнал окна (вопросов нет);
    * `kind="missing"` — запускать нечего, честно сообщаем.
    """

    action: pm_buttons.Action
    kind: str
    command: list[str]
    problem: str = ""

    @property
    def title(self) -> str:
        return self.action.label


def project_python(project_dir: Path | str = PROJECT_ROOT) -> str:
    """Python проекта: .venv → venv → тот, чем запущено окно."""
    root = Path(project_dir)
    for candidate in (root / ".venv" / "Scripts" / "python.exe",
                      root / "venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def plan_for(action: pm_buttons.Action,
             project_dir: Path | str = PROJECT_ROOT) -> RunPlan:
    """Во что превращается действие: что запустить и как."""
    root = Path(project_dir)

    if action.kind == "macro":
        for folder in pm_buttons.MACRO_FOLDERS:
            target = root / folder / action.target
            if target.exists():
                return RunPlan(action, "macro", [str(target)])
        where = root / pm_buttons.MACRO_FOLDERS[0] / action.target
        return RunPlan(action, "missing", [],
                       f"макроса нет: {where} (запусти пункт 28)")

    if action.kind == "bat":
        target = root / action.target_path
        if not target.exists():
            return RunPlan(action, "missing", [], f"файла нет: {target}")
        return RunPlan(action, "window", [str(target)])

    python = project_python(root)
    command = [python, "-m", action.target]
    if action.arguments:
        command += action.arguments.split()
    return RunPlan(action, "inline", command)


def plans(project_dir: Path | str = PROJECT_ROOT) -> list[RunPlan]:
    """Планы для всех кнопок окна (в порядке групп)."""
    return [plan_for(action, project_dir) for action in pm_buttons.pane_actions()]


def grouped_plans(project_dir: Path | str = PROJECT_ROOT
                  ) -> list[tuple[str, list[RunPlan]]]:
    """Планы по группам — так же, как в панели плагина."""
    groups: list[tuple[str, list[RunPlan]]] = []
    for plan in plans(project_dir):
        for name, items in groups:
            if name == plan.action.group:
                items.append(plan)
                break
        else:
            groups.append((plan.action.group, [plan]))
    return groups


def header_lines(data_root: Path | str = DATA_ROOT,
                 project_dir: Path | str = PROJECT_ROOT) -> list[str]:
    """Строки шапки окна: где данные, где код, есть ли PowerMill."""
    lines = [
        f"Код:     {Path(project_dir)}",
        f"Данные:  {Path(data_root)}",
    ]
    from src import pm_com

    session, message = pm_com.connect()
    if session is not None:
        lines.append(f"PowerMill: подключён (версия {session.version})")
        try:
            counts = session.counts()
            tools = counts.get("tools", 0)
            toolpaths = counts.get("toolpaths", 0)
            lines.append(f"Проект: инструментов {tools}, траекторий {toolpaths}")
        except Exception:                                     # noqa: BLE001
            pass
    else:
        lines.append(f"PowerMill: не подключён — {message}")
    return lines


def run_macro(macro: Path) -> list[str]:
    """Выполняет макрос в PowerMill и возвращает строки журнала."""
    from src import pm_com

    session, message = pm_com.connect()
    if session is None:
        return [
            "(!) PowerMill не отвечает: " + message,
            "    Открой проект в PowerMill и повтори — или используй кнопки на",
            "    ленте PowerMill (пункт 34), они работают изнутри.",
        ]
    command = f'MACRO "{str(macro).replace(chr(92), "/")}"'
    ok, note = session.execute(command)
    return [
        f"{'✔' if ok else '✘'} PowerMill: {command}",
        f"   {note}" if note else "   (ответа нет)",
    ]


# --------------------------------------------------------------------------
# Окно
# --------------------------------------------------------------------------
class AppWindow:
    """Окно приложения: кнопки, журнал, состояние."""

    def __init__(self, project_dir: Path | str = PROJECT_ROOT):
        import tkinter as tk

        self.tk = tk
        self.project_dir = Path(project_dir)
        self.queue: Queue[str] = Queue()
        self.process: subprocess.Popen | None = None
        self.busy = False

        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(860, 560)
        self._set_icon()

        self._build_header()
        self._build_body()
        self._build_footer()
        self.root.after(150, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_icon(self) -> None:
        """Иконка окна: PNG рядом с кодом (Tk 8.6 читает PNG сам)."""
        icon = PROJECT_ROOT / "assets" / "app_icon.png"
        if not icon.exists():
            return
        try:
            self.icon = self.tk.PhotoImage(file=str(icon))
            self.root.iconphoto(True, self.icon)
        except Exception:                                     # noqa: BLE001
            pass                      # иконка — украшение, из-за неё не падаем

    # ---------------- сборка окна ----------------
    def _build_header(self) -> None:
        tk = self.tk
        frame = tk.Frame(self.root, padx=10, pady=8)
        frame.pack(fill="x")
        tk.Label(frame, text="PowerMill AI", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(frame, text="Ассистент технолога: режимы, фреза, черновая, "
                            "проверки, NC",
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.state_label = tk.Label(frame, text="", justify="left",
                                    font=("Consolas", 9), fg="#333333")
        self.state_label.pack(anchor="w", pady=(6, 0))
        self.refresh_state()

    def _build_body(self) -> None:
        tk = self.tk
        body = tk.Frame(self.root, padx=10)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body)
        left.pack(side="left", fill="y")
        for group, plans in grouped_plans(self.project_dir):
            tk.Label(left, text=group, font=("Segoe UI", 9, "bold"),
                     anchor="w").pack(fill="x", pady=(8, 2))
            for plan in plans:
                text = plan.title
                if plan.kind == "macro":
                    text = "▶ " + text
                button = tk.Button(left, text=text, width=34, anchor="w",
                                   command=lambda plan=plan: self.start(plan))
                button.pack(fill="x", pady=1)
                if plan.problem:
                    button.configure(state="disabled")
                    tk.Label(left, text="   " + plan.problem, fg="#a00000",
                             font=("Segoe UI", 8), anchor="w",
                             wraplength=260, justify="left").pack(fill="x")

        right = tk.Frame(body, padx=8)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Журнал", font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x")
        self.log = tk.Text(right, wrap="none", font=("Consolas", 9),
                           background="#111111", foreground="#e0e0e0")
        self.log.pack(fill="both", expand=True)
        scroll = tk.Scrollbar(right, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set, state="disabled")

    def _build_footer(self) -> None:
        tk = self.tk
        frame = tk.Frame(self.root, padx=10, pady=8)
        frame.pack(fill="x")
        self.status = tk.Label(frame, text="Готов", anchor="w", font=("Segoe UI", 9))
        self.status.pack(side="left")
        tk.Button(frame, text="Остановить", command=self.stop).pack(side="right", padx=2)
        tk.Button(frame, text="Проверка компьютера",
                  command=lambda: self.start_key("doctor")).pack(side="right", padx=2)
        tk.Button(frame, text="Отчёты",
                  command=lambda: self.start_key("reports")).pack(side="right", padx=2)
        tk.Button(frame, text="Очистить журнал",
                  command=self.clear_log).pack(side="right", padx=2)

    # ---------------- журнал ----------------
    def write(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        # чтобы окно не росло бесконечно, старые строки убираем
        total = int(self.log.index("end-1c").split(".")[0])
        if total > LOG_LIMIT_LINES:
            self.log.delete("1.0", f"{total - LOG_LIMIT_LINES}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def write_many(self, lines: list[str]) -> None:
        for line in lines:
            self.write(line)

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def refresh_state(self) -> None:
        self.state_label.configure(text="\n".join(header_lines()))

    # ---------------- запуск ----------------
    def start_key(self, key: str) -> None:
        action = pm_buttons.by_key(key)
        if action is None:
            self.write(f"(!) нет действия «{key}»")
            return
        self.start(plan_for(action, self.project_dir))

    def start(self, plan: RunPlan) -> None:
        if self.busy:
            self.write("Сейчас уже идёт другое действие — нажми «Остановить» "
                       "или дождись конца.")
            return
        self.write("")
        self.write(f"=== {plan.title} ===")

        if plan.kind == "missing":
            self.write("(!) " + plan.problem)
            return

        if plan.kind == "macro":
            self.busy = True
            self.set_status(f"Выполняю: {plan.title}")
            threading.Thread(target=self._macro_thread, args=(plan,),
                             daemon=True).start()
            return

        if plan.kind == "window":
            # отдельное окно: сценарий спрашивает технолога
            try:
                subprocess.Popen(plan.command, cwd=str(self.project_dir),
                                 creationflags=getattr(subprocess,
                                                       "CREATE_NEW_CONSOLE", 0))
                self.write("Открыл отдельное окно — отвечай на вопросы там.")
                self.write("Когда закончится, нажми «Отчёты», чтобы прочитать отчёт.")
            except OSError as error:
                self.write(f"(!) не удалось открыть: {error}")
            return

        # inline: вывод построчно сюда
        self.busy = True
        self.set_status(f"Работаю: {plan.title}")
        threading.Thread(target=self._inline_thread, args=(plan,),
                         daemon=True).start()

    def _macro_thread(self, plan: RunPlan) -> None:
        try:
            lines = run_macro(Path(plan.command[0]))
        except Exception as error:                                # noqa: BLE001
            lines = [f"(!) ошибка при выполнении макроса: {error}"]
        for line in lines:
            self.queue.put(line)
        self.queue.put("__DONE__")

    def _inline_thread(self, plan: RunPlan) -> None:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("APP_MODE", "eco")
        try:
            self.process = subprocess.Popen(
                plan.command, cwd=str(self.project_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1)
        except OSError as error:
            self.queue.put(f"(!) не удалось запустить: {error}")
            self.queue.put("__DONE__")
            return

        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.queue.put(line.rstrip("\n"))
        self.process.wait()
        self.queue.put(f"[закончилось, код {self.process.returncode}]")
        self.queue.put("__DONE__")

    def _drain_queue(self) -> None:
        try:
            while True:
                line = self.queue.get_nowait()
                if line == "__DONE__":
                    self.busy = False
                    self.set_status("Готов")
                    self.refresh_state()
                    continue
                self.write(line)
        except Empty:
            pass
        self.root.after(150, self._drain_queue)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.write("Остановил запущенный сценарий.")
        self.busy = False
        self.set_status("Готов")

    def on_close(self) -> None:
        self.stop()
        self.root.destroy()

    def run(self) -> None:
        self.write("PowerMill AI: окно готово.")
        self.write("Кнопки с «▶» выполняются внутри PowerMill; кнопки «— окно»")
        self.write("открывают сценарий отдельным окном, потому что он спрашивает")
        self.write("материал, фрезу и припуски.")
        self.root.mainloop()


def main() -> int:
    try:
        window = AppWindow()
    except Exception as error:                                    # noqa: BLE001
        print("Не смог открыть окно приложения:", error)
        print("Проверь, что установлен Python с поддержкой Tk (обычная установка).")
        return 1
    window.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

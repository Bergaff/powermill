"""
Проверка связи приложения и PowerMill (пункт 41).

Зачем отдельно от пункта 40
---------------------------
Пункт 40 смотрит на компьютер целиком: Python, библиотеки, папки. А этот пункт
отвечает на один вопрос, от которого зависит всё остальное: **могу ли я сейчас
управлять PowerMill** — и доказывает ответ делом, а не догадкой.

Как доказывается связь (без выдумок)
------------------------------------
1. есть ли `pywin32` — мост к COM (пункт 27);
2. идёт ли процесс PowerMill (по списку процессов, а не «на глаз»);
3. цепляемся к **работающему** PowerMill (`GetActiveObject`) и читаем оттуда
   версию и содержимое проекта — это уже настоящее чтение;
4. **двусторонняя проверка делом**: отправляем в PowerMill наш макрос
   `PM_AI_TEST.mac`, который сам записывает файл-отметку, и ждём, что файл
   обновится. Файл пишет **сам PowerMill**, поэтому обновление файла — это
   доказательство, что PowerMill получил нашу команду и выполнил её.

Если на любом шаге не получилось — говорим, на каком именно и что делать
(обычно: поднять мост пунктом 27, открыть проект в PowerMill, перезапустить окно).
Проект при этом не меняется: макрос только пишет свои файлы-отметки.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from src import pm_com, pm_macro

# Сколько ждём, что PowerMill выполнит наш тестовый макрос
ROUNDTRIP_TIMEOUT = 25.0
POLL_INTERVAL = 0.5


@dataclass
class LinkReport:
    """Итог проверки связи."""

    steps: list[tuple[str, str, str]] = field(default_factory=list)  # (шаг, ok|fail|warn, текст)
    advice: list[str] = field(default_factory=list)
    roundtrip: bool | None = None        # прошла ли проверка делом
    version: str = ""

    @property
    def connected(self) -> bool:
        return any(status == "ok" for step, status, _ in self.steps
                   if step == "com")

    @property
    def ready(self) -> bool:
        return all(status != "fail" for _step, status, _text in self.steps)

    def add(self, step: str, status: str, text: str) -> None:
        self.steps.append((step, status, text))

    def format(self) -> str:
        marks = {"ok": "✔", "fail": "✘", "warn": "•", "skip": "—"}
        titles = {
            "pywin32": "Мост к COM (pywin32)",
            "process": "PowerMill запущен",
            "com": "Связь с приложением PowerMill",
            "project": "Чтение проекта",
            "roundtrip": "Проверка делом (макрос записал файл)",
        }
        lines = []
        for step, status, text in self.steps:
            lines.append(f"  {marks.get(status, '?')} {titles.get(step, step)}: {text}")
        if self.advice:
            lines.append("")
            lines.append("Что делать:")
            lines.extend(f"  • {item}" for item in self.advice)
        return "\n".join(lines)

    def summary(self) -> str:
        if self.roundtrip is True:
            return "Связь есть и проверена делом: PowerMill выполнил нашу команду."
        if self.roundtrip is False:
            return "Связь односторонняя: проект читается, но команду PowerMill не выполнил."
        if self.connected:
            return "PowerMill отвечает на чтение. Проверку делом не запускали."
        return "Связи с PowerMill нет — смотри шаги выше."


def _process_hint() -> str:
    """Подсказка, идёт ли процесс PowerMill (psutil, иначе — не знаем)."""
    try:
        import psutil
    except ImportError:
        return "проверить нечем (нет psutil — пункт 27 его ставит)"
    try:
        found = []
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if "powermill" in name or "pmill" in name:
                found.append(proc.info["name"])
        if found:
            return "да: " + ", ".join(sorted(set(found)))
        return "нет — PowerMill не запущен"
    except Exception as error:                                # noqa: BLE001
        return f"не смог посмотреть процессы: {error}"


def _trace_state(path: Path) -> tuple[float, int]:
    """Время и размер файла-отметки.

    Двух признаков, а не одного, потому что у времени изменения бывает грубая
    точность: если PowerMill запишет файл в ту же секунду, «время больше» может
    не сработать. Размер — второй признак (текст отметок у нас разный).
    """
    try:
        info = path.stat()
        return info.st_mtime, info.st_size
    except OSError:
        return 0.0, -1          # файла нет — любое появление считается изменением


def _trace_states() -> dict[Path, tuple[float, int]]:
    return {path: _trace_state(path) for path in pm_macro.trace_files()}


def _wait_for_trace(before: dict[Path, tuple[float, int]],
                    timeout: float = ROUNDTRIP_TIMEOUT) -> Path | None:
    """Ждём, что PowerMill обновил любой из файлов-отметок."""
    deadline = time.time() + timeout
    while True:
        for path, was in before.items():
            now = _trace_state(path)
            if now[0] > was[0] + 0.001 or now[1] != was[1]:
                return path
        if time.time() >= deadline:
            return None
        time.sleep(POLL_INTERVAL)


def check_project(session) -> tuple[bool, str]:
    """Читает проект: сколько чего. Это уже работающее чтение, не картинка."""
    try:
        counts = session.counts()
    except Exception as error:                                # noqa: BLE001
        return False, f"проект прочитать не удалось: {error}"
    parts = [f"{name}: {counts.get(name, 0)}" for name in
             ("models", "tools", "boundaries", "patterns", "toolpaths", "ncprograms")]
    return True, ", ".join(parts)


def run(with_roundtrip: bool = True) -> LinkReport:
    """Полная проверка связи. `with_roundtrip=False` — только чтение."""
    report = LinkReport()

    bridges = pm_com.bridges()
    if bridges.get("pywin32"):
        report.add("pywin32", "ok", "модуль на месте")
    else:
        report.add("pywin32", "fail", "не установлен в этом Python")
        report.advice.append("Запусти пункт 27 меню — он поставит pywin32 в тот же "
                             "Python, из которого работает приложение.")

    report.add("process", "warn", _process_hint())

    session, message = pm_com.connect()
    if session is None:
        report.add("com", "fail", message)
        report.advice.append("Открой PowerMill с проектом и запусти проверку снова "
                             "(окно приложения проверяет связь при каждом запуске).")
        return report

    report.add("com", "ok", f"подключён, версия {session.version}")
    report.version = session.version

    ok, detail = check_project(session)
    report.add("project", "ok" if ok else "fail", detail)
    if not ok:
        report.advice.append("Похоже, в PowerMill не открыт проект: открой проект "
                             "(Файл -> Открыть) и повтори проверку.")

    if not with_roundtrip:
        report.add("roundtrip", "skip", "не запускали (проверка только чтением)")
        return report

    # --- проверка делом ---
    macro = pm_macro.MACRO_DIR / "PM_AI_TEST.mac"
    if not macro.exists():
        try:
            pm_macro.write_all()
        except OSError as error:
            report.add("roundtrip", "fail", f"не смог записать макрос: {error}")
            return report
    if not macro.exists():
        report.add("roundtrip", "fail", f"макроса нет: {macro}")
        report.advice.append("Запусти пункт 28 меню — он создаёт макросы ассистента.")
        return report

    before = _trace_states()
    command = f'MACRO "{str(macro).replace(chr(92), "/")}"'
    ok, note = session.execute(command)
    if not ok:
        report.add("roundtrip", "fail", f"команду не приняли: {note}")
        report.roundtrip = False
        report.advice.append("Если PowerMill открыт и проект на месте, пришли этот "
                             "текст — подберу другой способ отправки команды.")
        return report

    updated = _wait_for_trace(before)
    if updated is not None:
        report.add("roundtrip", "ok",
                   f"PowerMill выполнил наш макрос и записал {updated.name} — "
                   "связь работает в обе стороны")
        report.roundtrip = True
    else:
        report.add("roundtrip", "fail",
                   f"за {ROUNDTRIP_TIMEOUT:.0f} с файлы-отметки не обновились")
        report.roundtrip = False
        report.advice.append("Возможные причины: макрос ждёт нажатия (MACRO PAUSE) — "
                             "посмотри окно PowerMill; или включён режим, где макросы "
                             "не выполняются.")
    return report


def format_report(report: LinkReport) -> str:
    """Отчёт для файла (пункт 29)."""
    lines = [
        "PowerMill AI — проверка связи с PowerMill (пункт 41)",
        time.strftime("Проверено: %d.%m.%Y %H:%M"),
        "",
        report.format(),
        "",
        "ИТОГ: " + report.summary(),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Проверка из командной строки/батника: код 0 — связь есть."""
    print("=" * 64)
    print("  ПУНКТ 41 — ПРОВЕРКА СВЯЗИ ПРИЛОЖЕНИЯ И POWERMILL")
    print("=" * 64)
    print()
    report = run()
    print(report.format())
    print()
    print("ИТОГ: " + report.summary())

    from config import OUTPUT_DIR

    path = Path(OUTPUT_DIR) / "pm_link_report.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_report(report), encoding="utf-8")
        print()
        print(f"📝 Отчёт: {path}")
    except OSError as error:
        print(f"(!) отчёт не записался: {error}")

    if report.roundtrip is True or (report.connected and report.ready):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

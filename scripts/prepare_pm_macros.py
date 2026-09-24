"""
Макросы «PowerMill AI» внутри PowerMill (пункт 28 меню).

Создаёт два макроса и кладёт их туда, где PowerMill их видит:

* PM_AI_TEST.mac     — самопроверка моста: файлы + запуск .bat + пауза;
* PM_AI_ASK.mac      — меню «что нужно», вопрос и показ ответа в окне PowerMill;
* PM_AI_SNAPSHOT.mac — снимок проекта (модели, границы, инструменты, траектории).

Запуск в PowerMill: вкладка «Макрос» -> Выполнить -> нужный файл.
Кнопку можно закрепить: правой кнопкой на ленте -> «Настроить ленту» ->
Макрос -> добавить. Подробная инструкция печатается ниже.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pm_macro                        # noqa: E402
from src.applog import start_log                # noqa: E402

REPORT_FILE = None                              # ставится в main()


MACRO_NAMES = ("PM_AI_TEST.mac", "PM_AI_ASK.mac", "PM_AI_SNAPSHOT.mac")


def main() -> int:
    from config import OUTPUT_DIR

    report_path = Path(OUTPUT_DIR) / "pm_macros_report.txt"
    printer = _Tee(report_path)

    log = start_log("prepare_pm_macros")
    printer.print("=" * 60)
    printer.print("  МАКРОСЫ PowerMill AI (кнопка ассистента внутри PowerMill)")
    printer.print("=" * 60)
    printer.print()
    printer.print(f"Лог: {log}")
    printer.print()

    written = pm_macro.write_all()
    printer.print("Создано:")
    for path in written:
        printer.print(f"  {path}")
    printer.print()

    folders = pm_macro.power_mill_macro_folders()
    copied: list[Path] = []
    failed: list[Path] = []
    if folders:
        printer.print("Копирую в папки макросов PowerMill:")
        for folder in folders:
            for name in MACRO_NAMES:
                source = pm_macro.MACRO_DIR / name
                if not source.exists():
                    continue
                try:
                    shutil.copy2(source, folder / name)
                    copied.append(folder / name)
                except OSError as error:
                    failed.append(folder / name)
                    printer.print(f"  (!) {folder}: {error}")
        for path in copied:
            printer.print(f"  ✔ {path}")
    else:
        printer.print("Папки макросов PowerMill не нашёл — макросы лежат здесь:")
        printer.print(f"  {pm_macro.MACRO_DIR}")
        printer.print("В PowerMill добавь этот путь: Макрос -> Пути макросов (Macro Paths).")

    if failed:
        printer.print()
        printer.print("Часть копий не удалась (нужны права администратора).")
        printer.print("Ничего страшного: запусти макрос прямо из папки:")
        printer.print(f"  {pm_macro.MACRO_DIR}")

    printer.print()
    printer.print("=" * 60)
    printer.print("  КАК ПОЛЬЗОВАТЬСЯ")
    printer.print("=" * 60)
    printer.print()
    printer.print("ШАГ 1 — проверь мост (10 секунд):")
    printer.print(f"  {pm_macro.MACRO_DIR}\\PM_AI_TEST.mac")
    printer.print("  Макрос запишет файл, прочитает его и откроет тестовое окно.")
    printer.print("  Если он показал «МОСТ РАБОТАЕТ ПОЛНОСТЬЮ» — идём дальше.")
    printer.print()
    printer.print("ШАГ 2 — сам ассистент. В PowerMill: вкладка «Макрос» -> «Выполнить» ->")
    printer.print(f"  {pm_macro.MACRO_DIR}\\PM_AI_ASK.mac")
    printer.print()
    printer.print("  • появится меню: справка / макрос / ошибка / режимы резания;")
    printer.print("  • введи текст вопроса;")
    printer.print("  • ассистент откроет своё окно, посчитает ответ;")
    printer.print("  • нажми RESUME в PowerMill — ответ появится в окне сообщений.")
    printer.print()
    printer.print("Снимок проекта: PM_AI_SNAPSHOT.mac — ассистент сам прочитает объекты")
    printer.print("(модели, границы, инструменты, траектории) и покажет проверки.")
    printer.print()
    printer.print("Чтобы закрепить макрос на кнопке:")
    printer.print("  правой кнопкой по ленте -> «Настроить ленту» -> категория «Макрос»;")
    printer.print("  либо File -> Options -> Macro Paths: добавь папку")
    printer.print(f"  {pm_macro.MACRO_DIR}")
    printer.print()
    printer.print(f"Отчёт сохранён: {report_path}")
    printer.print("Открыть его можно пунктом 29 меню («Показать отчёты»).")
    printer.flush()
    return 0


class _Tee:
    """Печатает на экран и одновременно пишет отчёт в файл (для пункта 29)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lines: list[str] = []
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def print(self, *parts, **kwargs) -> None:
        text = " ".join(str(p) for p in parts)
        print(text, **kwargs)
        self.lines.append(text)

    def flush(self) -> None:
        try:
            self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())

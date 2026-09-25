"""
Доставить нужные библиотеки (пункт 43 меню).

Зачем: у человека может быть установлено приложение без библиотек (или он
выбрал «только самое необходимое»), и тогда окно и проверка связи честно
говорят «pywin32 не установлен». Этот пункт ставит недостающее **в тот же
Python, из которого работает программа** — именно поэтому кнопка в окне и
пункт меню делают одно и то же.

Что делает:
1. смотрит, что уже есть, а чего нет (по модулям, не по именам пакетов);
2. без `--all` ставит только обязательный набор (десятки мегабайт, пара минут):
   pywin32, psutil, requests, beautifulsoup4, lxml;
3. с `--all` дополнительно ставит тяжёлые (chromadb, sentence-transformers,
   faster-whisper, PyMuPDF, ollama) — это гигабайты и долго, лучше ночью;
4. `--check` — только показать состояние, ничего не ставить;
5. пишет отчёт `output\\install_packages_report.txt` (его можно прислать в чат).

Примеры (их запускают батники, вручную не нужно):
    python -m scripts.install_deps            # обязательные
    python -m scripts.install_deps --all      # обязательные + тяжёлые
    python -m scripts.install_deps --check    # только проверка
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import deps                                     # noqa: E402
from src.applog import start_log                         # noqa: E402


def ask_yes(question: str, default_yes: bool = True) -> bool:
    """Простой вопрос «да/нет» с понятным «по умолчанию»."""
    hint = "Д/н" if default_yes else "д/Н"
    while True:
        try:
            answer = input(f"{question} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default_yes
        if not answer:
            return default_yes
        if answer in ("д", "да", "y", "yes"):
            return True
        if answer in ("н", "нет", "n", "no"):
            return False
        print("  Ответь «д» или «н».")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Доставить библиотеки PowerMill AI")
    parser.add_argument("--all", action="store_true",
                        help="поставить и тяжёлые библиотеки (гигабайты)")
    parser.add_argument("--check", action="store_true",
                        help="только проверить, ничего не ставить")
    parser.add_argument("--yes", action="store_true", help="без вопросов")
    parser.add_argument("--python", help="в какой Python ставить (по умолчанию — текущий)")
    args = parser.parse_args(argv)

    log = start_log("install_deps")
    print("=" * 64)
    print("  БИБЛИОТЕКИ PowerMill AI — доставить недостающее (пункт 43)")
    print("=" * 64)
    print(f"  Python: {args.python or sys.executable}")
    print(f"  Лог:    {log}")
    print()
    print("Сейчас:")
    for spec, ok in deps.state():
        if ok:
            mark = "✔"
        else:
            mark = "✘" if not spec.heavy else "•"
        print(f"  {mark} {spec.package} — {spec.purpose}")
    print()

    lack = deps.missing(base=True)
    if args.check:
        text = deps.report_lines(args.python)
        saved = deps.save_report(text)
        print("\n".join(text[text.index("ИТОГ:") if "ИТОГ:" in text else -1:]))
        print(f"\n📝 Отчёт: {saved}")
        return 0 if not lack else 1

    if not lack:
        print("[OK] Обязательные библиотеки уже стоят — ставить нечего.")
    else:
        print("Не хватает: " + ", ".join(spec.package for spec in lack))
        print("Это то, без чего нет связи с PowerMill и разбора справки.")
        print()
        if not args.yes and not ask_yes("Поставить их сейчас?", True):
            print("Хорошо, ничего не ставил. Вернуться можно в любой момент — "
                  "пункт 43 меню или кнопка «Установить недостающее» в окне.")
            deps.save_report(deps.report_lines(args.python))
            return 1
        names = [spec.package for spec in lack]
        ok, message = deps.install(lack, python=args.python,
                                   log=lambda line: print("    " + line))
        print()
        print(("[OK] " if ok else "[!] ") + message)
        if not ok:
            still = deps.missing(base=True)
            print("Не встало: " + ", ".join(spec.package for spec in still) if still
                  else "Проверь интернет и повтори пункт 43.")
            saved = deps.save_report(deps.report_lines(args.python, names))
            print(f"\n📝 Отчёт: {saved}")
            print("Если ошибка про SSL/прокси или «не найден pip» — пришли отчёт "
                  "и лог в чат.")
            return 2
        print("Проверяю, что всё видно программе…")
        still = deps.missing(base=True)
        if still:
            print("  (!) всё ещё не видно: " + ", ".join(s.package for s in still))
            print("      Перезапусти окно приложения и проверь ещё раз.")
        else:
            print("  ✔ всё на месте")

    heavy = deps.missing(base=False, optional=True)
    if heavy and not args.all:
        print()
        print("По желанию (тяжёлое, для поиска по справке и разбора видео) нет: " +
              ", ".join(spec.package for spec in heavy))
        print("Это гигабайты и долго — лучше ночью, отдельной командой:")
        print("    python -m scripts.install_deps --all")

    text = deps.report_lines(args.python, None)
    saved = deps.save_report(text)
    print()
    print("Что делать дальше:")
    print("  1) закрой и снова открой окно приложения (кнопка «Перезапустить»);")
    print("  2) нажми «Связь с PowerMill» — она теперь проверит связь делом;")
    print("  3) все отчёты: start_menu.bat -> 29.")
    print()
    print(f"📝 Отчёт: {saved}")
    print("   Этот файл можно целиком прислать в чат.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

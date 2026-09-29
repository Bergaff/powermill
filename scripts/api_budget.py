"""
Расходы на ИИ и лимиты — пункт 46 меню.

Зачем: облачный ИИ (DeepSeek, OpenAI, OpenRouter…) стоит денег за каждый токен.
Этот пункт показывает, сколько уже израсходовано, и позволяет поставить границы,
после которых запросы **не уходят** в платный сервис — вместо ответа придёт
объяснение и подсказка переключиться на бесплатную локальную модель (пункт 22).

Что умеет:

    python -m scripts.api_budget                 # показать расходы и лимиты
    python -m scripts.api_budget --set           # поменять лимиты (спросит числа)
    python -m scripts.api_budget --report        # отчёт в output\\api_spend_report.txt
    python -m scripts.api_budget --reset         # обнулить счётчики (с подтверждением)
    python -m scripts.api_budget --limit-requests 50 --limit-daily-usd 0.3

Лимиты хранятся в том же файле, что и ключ (`api_key.json`), поэтому их видно
глазами и легко перенести на другой компьютер.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import api_budget, llm                           # noqa: E402
from src.applog import start_log                           # noqa: E402

# Понятные подписи для вопросов
PROMPTS: dict[str, tuple[str, str]] = {
    "daily_requests": ("Запросов в день (0 — без ограничения)",
                       "например 100"),
    "daily_cost_usd": ("Расход в день, долларов (0 — без ограничения)",
                       "например 0.50"),
    "monthly_cost_usd": ("Расход в месяц, долларов (0 — без ограничения)",
                         "например 5.00"),
    "max_tokens_per_request": ("Максимум токенов на один ответ",
                               "1024 — короче и дешевле, 2048 — как сейчас"),
}


def read_line(text: str) -> str:
    try:
        return input(text)
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def ask_number(key: str, current) -> float | int | None:
    title, hint = PROMPTS[key]
    default = current
    while True:
        raw = read_line(f"  {title} [{default}] ({hint}): ").strip().replace(",", ".")
        if not raw:
            return None                        # оставляем как было
        if raw.lower() in ("назад", "отмена", "q"):
            return None
        try:
            value = float(raw)
        except ValueError:
            print("     Нужно число, например 100 или 0.5")
            continue
        if value < 0:
            print("     Число не может быть отрицательным")
            continue
        if key == "max_tokens_per_request":
            return int(value)
        if key == "daily_requests":
            return int(value)
        return round(value, 4)


def ask_yes(question: str, default_yes: bool = False) -> bool:
    hint = "Д/н" if default_yes else "д/Н"
    while True:
        raw = read_line(f"{question} [{hint}]: ").strip().lower()
        if not raw:
            return default_yes
        if raw in ("д", "да", "y", "yes"):
            return True
        if raw in ("н", "нет", "n", "no"):
            return False
        print("  Ответь «д» или «н».")


def show_extras() -> None:
    """Про цены и про то, где что лежит — чтобы не искать."""
    price_in, price_out, known = api_budget.prices()
    print()
    print("Цены (за 1 млн токенов) — из файла настроек, иначе примерные:")
    if known:
        print(f"  вход ${price_in:.2f}, выход ${price_out:.2f}")
    else:
        print("  не заданы — считаю только токены, деньги не оцениваю")
    print(f"  ключ и лимиты: {api_budget.settings_path()}")
    print(f"  счётчики:      {api_budget.SPEND_FILE}")
    print(f"  отчёт:         {api_budget.REPORT_FILE}")


def show() -> int:
    settings = llm.load_settings()
    print("=" * 62)
    print("  РАСХОДЫ НА ИИ И ЛИМИТЫ (пункт 46)")
    print("=" * 62)
    print(f"  Режим ИИ: {'облачный API' if settings['backend'] == 'api' else 'локальная Ollama (бесплатно)'}")
    if settings["backend"] != "api":
        print("  Сейчас платить не за что: работает локальная модель.")
        print("  Расходы ниже — история (если облачным ИИ пользовались раньше).")
    print()
    for line in api_budget.summary_lines(settings):
        print("  " + line if not line.startswith("Расходы") else line)
    show_extras()
    print()
    print("Что можно сделать:")
    print("  • поменять лимиты:  python -m scripts.api_budget --set")
    print("  • отчёт по дням:    python -m scripts.api_budget --report")
    print("                      (или пункт 29 меню — там он тоже есть)")
    print("  • обнулить счётчики: --reset (лимиты и ключ не трогаются)")
    return 0


def set_limits(args) -> int:
    current = api_budget.limits()
    values: dict = {}

    if args.limit_requests is not None:
        values["daily_requests"] = int(args.limit_requests)
    if args.limit_daily_usd is not None:
        values["daily_cost_usd"] = float(args.limit_daily_usd)
    if args.limit_monthly_usd is not None:
        values["monthly_cost_usd"] = float(args.limit_monthly_usd)
    if args.max_tokens is not None:
        values["max_tokens_per_request"] = int(args.max_tokens)

    if not values:
        print("Сейчас стоят такие лимиты:")
        for key in PROMPTS:
            print(f"  {PROMPTS[key][0]}: {current.get(key)}")
        print()
        print("Enter — оставить как есть. «назад» — ничего не менять.")
        print()
        for key in PROMPTS:
            answer = ask_number(key, current.get(key))
            if answer is not None:
                values[key] = answer

    if values.get("daily_cost_usd") and values.get("monthly_cost_usd"):
        if float(values["daily_cost_usd"]) > float(values["monthly_cost_usd"]):
            print("  (!) расход в день больше расхода в месяц — так не бывает,")
            print("      считаю лимит месяца больше дневного на всякий случай")
            values["monthly_cost_usd"] = round(
                float(values["daily_cost_usd"]) * 31, 2)

    extra = {}
    if args.price_input is not None:
        extra["price_input_per_m"] = float(args.price_input)
    if args.price_output is not None:
        extra["price_output_per_m"] = float(args.price_output)

    if not values and not extra:
        print("Ничего не менял.")
        return 0

    path = api_budget.update_limits(values, extra)
    print()
    print("Сохранено в " + str(path))
    print("Теперь так:")
    for line in api_budget.summary_lines():
        if "лимиты:" in line:
            print("  " + line.strip())
    api_budget.save_report()
    print()
    print("Важно: когда лимит исчерпан, запрос к платному сервису НЕ уходит —")
    print("приходит объяснение и подсказка переключиться на локальную модель")
    print("(пункт 22 меню). Продолжить работу можно всегда, вопрос только в деньгах.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Расходы на облачный ИИ и лимиты (пункт 46)")
    parser.add_argument("--show", action="store_true",
                        help="показать расходы и лимиты (это же — по умолчанию)")
    parser.add_argument("--set", action="store_true",
                        help="поменять лимиты (спросит числа)")
    parser.add_argument("--report", action="store_true",
                        help="записать отчёт и показать путь")
    parser.add_argument("--reset", action="store_true",
                        help="обнулить счётчики (лимиты и ключ не трогает)")
    parser.add_argument("--yes", action="store_true", help="без вопросов")
    parser.add_argument("--limit-requests", type=int, default=None,
                        help="лимит запросов в день")
    parser.add_argument("--limit-daily-usd", type=float, default=None,
                        help="лимит расхода в день, $")
    parser.add_argument("--limit-monthly-usd", type=float, default=None,
                        help="лимит расхода в месяц, $")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="потолок токенов на один ответ")
    parser.add_argument("--price-input", type=float, default=None,
                        help="своя цена входа за 1 млн токенов, $")
    parser.add_argument("--price-output", type=float, default=None,
                        help="своя цена выхода за 1 млн токенов, $")
    args = parser.parse_args(argv)

    log = start_log("api_budget")
    print(f"Лог: {log}")

    if args.report:
        path = api_budget.save_report()
        print(f"📝 Отчёт: {path}")
        print("   Его можно целиком прислать в чат.")
        return 0

    if args.reset:
        data = api_budget.load()
        if not args.yes:
            print(f"Сейчас счётчики: {data['totals']['requests']} запросов.")
            if not ask_yes("Обнулить счётчики расходов?", False):
                print("Ничего не менял.")
                return 0
        api_budget.reset()
        print("Счётчики обнулены. Лимиты и ключ не тронуты.")
        return 0

    if args.set or any(value is not None for value in
                       (args.limit_requests, args.limit_daily_usd,
                        args.limit_monthly_usd, args.max_tokens,
                        args.price_input, args.price_output)):
        return set_limits(args)

    return show()


if __name__ == "__main__":
    sys.exit(main())

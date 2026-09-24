"""
Настройка облачного ИИ по API (пункт 21 меню).

Зачем: локальная модель на 16 ГБ путается в синтаксисе PML и таблицах, а
облачная — нет. Выдержки из справки (RAG) уходят ей тем же путём, что и
локальной: разница только в «мозге», который их читает.

Ключ сохраняется в `E:\\powermill-ai\\api_key.json` — файл лежит ВНЕ репозитория,
в Git не попадает. Прервать настройку можно словом «меню».
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import llm                                     # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import classify, read_line             # noqa: E402

ORDER = ["openai", "openrouter", "deepseek", "groq", "custom"]


def choose_provider() -> str | None:
    print("=" * 60)
    print("  ПОДКЛЮЧЕНИЕ ИИ ПО API")
    print("  Справка остаётся у тебя: на сервер уходят только выдержки по вопросу")
    print("=" * 60)
    print()
    for i, key in enumerate(ORDER, 1):
        info = llm.PROVIDERS[key]
        print(f"  {i}. {info['title']}")
        print(f"     где взять ключ: {info['how']}")
        if info["base_url"]:
            print(f"     адрес: {info['base_url']}, модель по умолчанию: {info['model']}")
    print()
    print("  0. Отмена")
    print()

    while True:
        answer = read_line(f"Выбери сервис (1-{len(ORDER)}, 0 — отмена): ")
        if answer is None:
            return None
        action = classify(answer)
        if action == "menu" or answer.strip() == "0":
            return None
        if action == "skip":
            print("Не понял. Нужен номер из списка.")
            continue
        if answer.strip().isdigit() and 1 <= int(answer.strip()) <= len(ORDER):
            return ORDER[int(answer.strip()) - 1]
        print(f"Нужен номер от 1 до {len(ORDER)} (или 0 — отмена).")


def ask_key(provider: str) -> str | None:
    info = llm.PROVIDERS[provider]
    print()
    print(f"Вставь ключ ({info['key_hint']}).")
    print("Ключ виден только тебе и сохраняется вне репозитория.")
    value = read_line("Ключ (Enter — отмена): ")
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value


def main() -> int:
    log = start_log("setup_api")
    print(f"Лог этого запуска: {log}")
    print()

    provider = choose_provider()
    if not provider:
        print("Отменено. Настройки не изменились.")
        return 0

    info = llm.PROVIDERS[provider]
    base_url = info["base_url"]
    model = info["model"]

    if provider == "custom":
        base_url = (read_line("Адрес сервиса (например https://сервер/v1): ") or "").strip()
        if not base_url:
            print("Без адреса настроить нельзя. Отменено.")
            return 2
        model = (read_line("Название модели: ") or "").strip()
        if not model:
            print("Без названия модели настроить нельзя. Отменено.")
            return 2

    api_key = ask_key(provider)
    if not api_key:
        print("Ключ не введён — отменено.")
        return 0

    # модель можно переопределить (например, для кода взять другую)
    print()
    entered_model = (read_line(f"Модель [Enter = {model}]: ") or "").strip()
    if entered_model:
        model = entered_model

    print()
    print("Проверяю ключ коротким запросом...")
    path = llm.save_settings(provider, base_url, model, api_key)

    settings = llm.load_settings()
    rc = llm.test_connection(settings)
    print()
    if rc == 0:
        print("✅ Готово! Чат будет отвечать этой моделью.")
        print("   Пункт 1 меню — чат, пункт 22 — вернуться на локальную модель.")
    else:
        print("⚠ Настройки сохранены, но проверка не прошла.")
        print("   Частые причины: ключ скопирован не полностью, нет интернета,")
        print("   у провайдера нет доступа к модели. Запусти пункт 21 снова.")
    print()
    print(f"Файл настроек (в Git не попадает): {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

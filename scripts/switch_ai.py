"""
Переключение «мозга»: локальная Ollama ↔ облачный API (пункт 22 меню).

Полезно, когда нужен и быстрый локальный ответ (черновик), и умный облачный
(финальный макрос). Настройки API при этом не теряются — меняется только режим.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LLM_MODEL                            # noqa: E402
from src import llm                                     # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import classify, read_line             # noqa: E402


def main() -> int:
    log = start_log("switch_ai")
    settings = llm.load_settings()

    print("=" * 58)
    print("  КАКОЙ ИИ ИСПОЛЬЗОВАТЬ")
    print("=" * 58)
    print(f"  Сейчас: {llm.describe_settings(settings)}")
    print(f"  Настройки API: {settings['source']}")
    print()
    print("  1. Локальная Ollama  — бесплатно, без интернета, слабее")
    print(f"     модель: {LLM_MODEL}")
    if settings.get("api_key"):
        print("  2. Облачный API      — умнее, нужен интернет")
        print(f"     модель: {settings.get('model') or '—'}")
    else:
        print("  2. Облачный API      — НЕ настроен (сначала пункт 21 меню)")
    print()
    print("  0. Ничего не менять")
    print(f"Лог: {log}")
    print()

    answer = read_line("Выбор (0-2): ")
    if answer is None:
        return 0
    action = classify(answer)
    if action == "menu":
        print("Ничего не изменил.")
        return 0

    choice = answer.strip()
    if choice == "1":
        backend = "local"
    elif choice == "2":
        if not settings.get("api_key"):
            print("API ещё не настроен — запусти пункт 21 меню.")
            return 2
        backend = "api"
    else:
        print("Ничего не изменил.")
        return 0

    data = {}
    try:
        import json
        data = json.loads(llm.API_KEY_FILE.read_text(encoding="utf-8")) \
            if llm.API_KEY_FILE.exists() else {}
    except Exception:  # noqa: BLE001
        data = {}
    data["backend"] = backend
    llm.API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json

    llm.API_KEY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    print()
    print("Проверяю, что выбранный ИИ отвечает...")
    rc = llm.test_connection(llm.load_settings())
    print()
    if rc == 0:
        print("✅ Переключено. Запускай чат: пункт 1 меню.")
    else:
        print("⚠ Переключил, но ИИ не отвечает — смотри сообщение выше.")
        print("   Вернуть локальную модель: этот же пункт 22, выбор 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

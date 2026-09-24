"""
Единая точка доступа к модели: локальная Ollama ИЛИ облачный API.

Зачем два варианта
------------------
* Локальная модель (Ollama, qwen2.5:3b/7b) — бесплатно, без интернета, но
  на 16 ГБ RAM и RTX 3060 она путается в синтаксисе PML и в таблицах.
* Облачный API — заметно умнее (не путает `CREATE BOUNDARY` с выдумкой) и не
  требует железа, но нужен интернет и ключ, а вопрос уходит на сервер.

Что делает этот модуль
----------------------
1. Читает настройки из `E:\\powermill-ai\\api_key.json` (файл создаёт
   `setup_api.bat`) и переменных окружения — ключ НЕ попадает в Git.
2. Умеет говорить с любым сервисом, совместимым с OpenAI
   (`/v1/chat/completions`): OpenAI, OpenRouter, DeepSeek, Groq, Together,
   GigaChat/локальные прокси, а также сама Ollama (она тоже умеет этот API).
3. Объясняет ошибки по-русски: нет ключа, неверный ключ (401), нет денег (402),
   лимит запросов (429), нет интернета, таймаут.
4. `python -m src.llm --test` проверяет подключение и печатает ответ модели.

Выбор: `LLM_BACKEND=api` (облако) или `local` (Ollama). Если стоит `auto`,
модуль берёт API при наличии ключа, иначе локальную модель.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import DATA_ROOT, LLM_MODEL

API_KEY_FILE = Path(os.getenv("POWERMILL_API_KEY_FILE", str(DATA_ROOT / "api_key.json")))
DEFAULT_TIMEOUT = float(os.getenv("LLM_API_TIMEOUT", "180"))

# Готовые настройки провайдеров: технологу достаточно выбрать номер в setup_api.bat
PROVIDERS: dict[str, dict] = {
    "openai": {
        "title": "OpenAI (самый известный)",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_hint": "sk-...",
        "how": "platform.openai.com -> API keys",
    },
    "openrouter": {
        "title": "OpenRouter (много моделей, один ключ)",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat",
        "key_hint": "sk-or-...",
        "how": "openrouter.ai -> Keys",
    },
    "deepseek": {
        "title": "DeepSeek (очень дешёвый, сильный в коде)",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "key_hint": "sk-...",
        "how": "platform.deepseek.com -> API keys",
    },
    "groq": {
        "title": "Groq (быстрый, есть бесплатный лимит)",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_hint": "gsk_...",
        "how": "console.groq.com -> API Keys",
    },
    "ollama": {
        "title": "Ollama на этом компьютере (бесплатно, без ключа)",
        "base_url": "http://localhost:11434/v1",
        "model": LLM_MODEL,
        "key_hint": "(любая строка, например local)",
        "how": "ничего не нужно",
    },
    "custom": {
        "title": "Свой адрес (любой OpenAI-совместимый сервис)",
        "base_url": "",
        "model": "",
        "key_hint": "ключ или любая строка",
        "how": "укажи адрес вида https://сервер/v1",
    },
}


# --------------------------------------------------------------------------
# Настройки
# --------------------------------------------------------------------------
def load_settings() -> dict:
    """Настройки API: файл → переменные окружения → провайдер по умолчанию."""
    data: dict = {}
    if API_KEY_FILE.exists():
        try:
            data = json.loads(API_KEY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}

    provider = os.getenv("LLM_PROVIDER", data.get("provider", "")) or ""
    preset = PROVIDERS.get(provider, {})

    base_url = (os.getenv("LLM_API_BASE") or data.get("base_url")
                or preset.get("base_url", "")).rstrip("/")
    model = os.getenv("LLM_API_MODEL") or data.get("model") or preset.get("model", "")
    api_key = os.getenv("LLM_API_KEY") or data.get("api_key", "")
    code_model = os.getenv("LLM_API_CODE_MODEL") or data.get("code_model") or model

    backend = os.getenv("LLM_BACKEND", data.get("backend", "auto")).lower()
    if backend == "auto":
        backend = "api" if (base_url and api_key) else "local"

    return {
        "backend": backend,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "code_model": code_model,
        "api_key": api_key,
        "timeout": float(data.get("timeout", DEFAULT_TIMEOUT)),
        "temperature": float(data.get("temperature", 0.2)),
        "source": str(API_KEY_FILE) if API_KEY_FILE.exists() else "настройки не заданы",
    }


def save_settings(provider: str, base_url: str, model: str, api_key: str,
                  code_model: str = "", backend: str = "api") -> Path:
    """Сохраняет настройки API в файл вне Git (ключ не попадёт в репозиторий)."""
    API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "code_model": code_model or model,
        "api_key": api_key,
        "backend": backend,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    API_KEY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    try:
        API_KEY_FILE.chmod(0o600)
    except OSError:
        pass
    return API_KEY_FILE


def describe_settings(settings: dict | None = None) -> str:
    """Короткое описание, какой ИИ сейчас используется (для статуса и чата)."""
    settings = settings or load_settings()
    if settings["backend"] == "api":
        key = settings.get("api_key") or ""
        tail = f"…{key[-4:]}" if len(key) > 4 else "(ключ не задан)"
        return (f"ИИ: API — {settings['provider'] or 'свой адрес'}, "
                f"модель {settings['model']}, ключ {tail}")
    return f"ИИ: локальная Ollama, модель {LLM_MODEL}"


# --------------------------------------------------------------------------
# Обращение к API
# --------------------------------------------------------------------------
def _friendly_error(status: int, body: str) -> str:
    """Понятное объяснение ошибки API вместо голого кода."""
    hints = {
        400: "Сервис не понял запрос. Проверь название модели.",
        401: "Ключ неверный или отозван. Запусти пункт 21 меню и введи ключ заново.",
        402: "На счету API закончились деньги — пополни баланс у провайдера.",
        403: "Доступ запрещён: возможно, ключ ограничен по стране или модели.",
        404: "Не найден адрес. Проверь base_url (должен кончаться на /v1).",
        413: "Запрос слишком большой — уменьши контекст (TOPK в config.py).",
        429: "Лимит запросов исчерпан. Подожди минуту или смени тариф.",
        500: "Сбой на стороне сервиса. Повтори запрос позже.",
        502: "Сервис недоступен (502). Повтори запрос позже.",
        503: "Сервис перегружен (503). Повтори запрос позже.",
    }
    hint = hints.get(status, "Неожиданный ответ сервиса.")
    snippet = (body or "").strip().replace("\n", " ")[:300]
    return f"❌ Ошибка API ({status}). {hint}\n   Ответ: {snippet}"


def chat(prompt: str, model: str = "", settings: dict | None = None,
         system: str = "", temperature: float | None = None,
         max_tokens: int = 2048) -> str:
    """Один запрос к API. Возвращает текст ответа или понятное сообщение об ошибке.

    Никогда не бросает исключений — чат не должен падать из-за сети.
    """
    settings = settings or load_settings()
    if not settings.get("base_url"):
        return ("❌ API не настроен: нет адреса сервиса.\n"
                "   Запусти пункт 21 меню (setup_api.bat) и выбери провайдера.")
    if not settings.get("api_key"):
        return ("❌ API не настроен: нет ключа.\n"
                "   Запусти пункт 21 меню (setup_api.bat) и вставь ключ.")

    model = model or settings.get("model", "")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": (settings.get("temperature", 0.2)
                        if temperature is None else temperature),
        "max_tokens": max_tokens,
        "stream": False,
    }
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
            # OpenRouter просит эти два заголовка, остальные их игнорируют
            "HTTP-Referer": "https://github.com/Bergaff/powermill",
            "X-Title": "PowerMill AI",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.get("timeout",
                                                                  DEFAULT_TIMEOUT)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        return _friendly_error(error.code, body)
    except urllib.error.URLError as error:
        return ("❌ Нет связи с сервисом ИИ.\n"
                f"   Причина: {error.reason}\n"
                "   Проверь интернет. Если это локальная Ollama — запущена ли она?")
    except TimeoutError:
        return ("❌ Сервис ИИ не ответил вовремя (таймаут).\n"
                "   Уменьши вопрос или увеличь таймаут: LLM_API_TIMEOUT=300")
    except Exception as error:  # noqa: BLE001
        return f"❌ Непредвиденная ошибка связи с API: {error}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"❌ Сервис вернул не JSON: {raw[:200]}"

    if isinstance(data, dict) and data.get("error"):
        message = data["error"].get("message", data["error"]) \
            if isinstance(data["error"], dict) else data["error"]
        return f"❌ Сервис отказал: {message}"

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return f"❌ Непонятный ответ сервиса: {raw[:300]}"


def pick_model(kind: str = "chat", settings: dict | None = None) -> str:
    """Модель для обычных вопросов ('chat') или для кода PML ('code')."""
    settings = settings or load_settings()
    if settings["backend"] == "api":
        return settings.get("code_model" if kind == "code" else "model", "")
    from config import LLM_CODE_MODEL, LLM_MODEL as LOCAL_CHAT

    return LLM_CODE_MODEL if kind == "code" else LOCAL_CHAT


# --------------------------------------------------------------------------
# Проверка подключения: python -m src.llm --test
# --------------------------------------------------------------------------
TEST_QUESTION = "Ответь одной короткой строкой: напиши слово Готово и свою модель."


def test_connection(settings: dict | None = None, verbose: bool = True) -> int:
    """Проверка связи с ИИ. Код возврата: 0 — работает, 2 — нет."""
    settings = settings or load_settings()
    if verbose:
        print("=" * 58)
        print("  ПРОВЕРКА ПОДКЛЮЧЕНИЯ К ИИ")
        print("=" * 58)
        print(f"  Режим      : {'облачный API' if settings['backend'] == 'api' else 'локальная Ollama'}")
        print(f"  Провайдер  : {settings.get('provider') or '—'}")
        print(f"  Адрес      : {settings.get('base_url') or '—'}")
        print(f"  Модель     : {settings.get('model') or '—'}")
        print(f"  Настройки  : {settings.get('source')}")
        print()

    if settings["backend"] != "api":
        return _test_local(settings, verbose)

    answer = chat(TEST_QUESTION, settings=settings, max_tokens=64, temperature=0)
    if verbose:
        print(f"  Ответ модели:\n    {answer[:400]}")
        print()
    if answer.startswith("❌"):
        if verbose:
            print("  [НЕ РАБОТАЕТ] ИИ по API не отвечает.")
            print("  Что сделать: пункт 21 меню — ввести ключ заново; проверь интернет.")
        return 2
    if verbose:
        print("  [OK] ИИ по API отвечает. Можно запускать чат: пункт 1 меню.")
    return 0


def _test_local(settings: dict, verbose: bool) -> int:
    """Проверка локальной Ollama (через её OpenAI-совместимый адрес)."""
    try:
        import ollama  # noqa: F401
    except ImportError:
        if verbose:
            print("  [!] Модуль ollama не установлен: pip install ollama")
            print("      Либо переключись на API: пункт 21 меню.")
        return 2

    local = dict(settings)
    local.update(base_url="http://localhost:11434/v1", api_key="local",
                 model=settings.get("model") or LLM_MODEL)
    answer = chat(TEST_QUESTION, settings=local, max_tokens=64, temperature=0)
    if verbose:
        print("  Ответ модели (локально):")
        print(f"    {answer[:400]}")
        print()
    if answer.startswith("❌"):
        if verbose:
            print("  [НЕ РАБОТАЕТ] Ollama не отвечает.")
            print("  Что сделать: запусти start_check.bat (пункт 7 меню) —")
            print("  он проверит, запущена ли Ollama и загружены ли модели.")
        return 2
    if verbose:
        print("  [OK] Локальная модель отвечает. Можно запускать чат: пункт 1 меню.")
    return 0


def main() -> int:
    import sys

    args = sys.argv[1:]
    if "--test" in args:
        return test_connection()
    if "--show" in args:
        settings = load_settings()
        print(describe_settings(settings))
        print(f"  настройки: {settings['source']}")
        print(f"  адрес:     {settings['base_url'] or '—'}")
        print(f"  модель:    {settings['model'] or '—'}")
        return 0
    if "--providers" in args:
        for key, info in PROVIDERS.items():
            print(f"{key:11} {info['title']}")
            print(f"            адрес: {info['base_url'] or '(свой)'}")
            print(f"            модель: {info['model'] or '(своя)'}")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

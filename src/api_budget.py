"""
Расходы на облачный ИИ и лимиты: чтобы «недешёвое удовольствие» не съело счёт.

Зачем это нужно
---------------
Локальная Ollama — бесплатно. Облачный API (DeepSeek, OpenAI, OpenRouter…) —
деньги за каждый токен. Без учёта легко получить неприятный сюрприз, поэтому:

1. **Считаем каждый запрос**: сколько запросов, сколько токенов пришло и ушло,
   во сколько это примерно обошлось. Счётчик по дням — в
   `DATA_ROOT\\api_spend.json` (то есть вне Git).
2. **Ставим лимиты ДО того, как потратили**: запросов в день, деньги в день и в
   месяц, максимум токенов на один ответ. Лимиты лежат в том же `api_key.json`,
   что и ключ (пункт 21), и правятся пунктом 46.
3. **Останавливаемся сами.** Если лимит исчерпан — запрос к сервису НЕ уходит:
   человек видит объяснение, сколько потрачено, и как вернуться на бесплатную
   локальную модель (пункт 22).

Честно про цены
---------------
Цены провайдеров меняются, а тарифы у людей разные. Поэтому здесь лежат
**примерные** цены (их можно переписать в `api_key.json`: `price_input_per_m`,
`price_output_per_m`). Если цены нет — считаем только токены и говорим прямо,
что деньги не оценены. Это оценка, а не счёт от провайдера.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from config import DATA_ROOT

SPEND_FILE = Path(os.getenv("POWERMILL_API_SPEND_FILE", str(DATA_ROOT / "api_spend.json")))
REPORT_FILE = Path(os.getenv("POWERMILL_API_REPORT_FILE",
                             str(DATA_ROOT / "output" / "api_spend_report.txt")))

# Лимиты по умолчанию — намеренно скромные: лучше упереться и поднять, чем
# однажды увидеть счёт. Меняются пунктом 46 меню.
DEFAULT_LIMITS: dict[str, float] = {
    "daily_requests": 100,          # запросов в день
    "daily_cost_usd": 0.50,         # долларов в день
    "monthly_cost_usd": 5.00,       # долларов в месяц
    "max_tokens_per_request": 2048,  # потолок одного ответа
    "warn_at_percent": 80,          # за сколько процентов предупреждать
}

# Примерные цены за 1 млн токенов (вход / выход), доллары.
# Это ОРИЕНТИР, а не тариф: проверяй у провайдера и правь в api_key.json.
PRICES: dict[str, tuple[float, float]] = {
    "deepseek": (0.27, 1.10),
    "openai": (0.15, 0.60),
    "openrouter": (0.27, 1.10),
    "groq": (0.59, 0.79),
    "ollama": (0.0, 0.0),
    "custom": (0.0, 0.0),
}


# --------------------------------------------------------------------------
# Хранилище счётчиков
# --------------------------------------------------------------------------
def _empty() -> dict:
    return {"days": {}, "totals": {"requests": 0, "prompt_tokens": 0,
                                   "completion_tokens": 0, "cost_usd": 0.0},
            "updated_at": ""}


def load() -> dict:
    """Счётчики расходов. Битый или пропавший файл — не повод падать."""
    if not SPEND_FILE.exists():
        return _empty()
    try:
        data = json.loads(SPEND_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("days", {})
    totals = data.setdefault("totals", {})
    for key in ("requests", "prompt_tokens", "completion_tokens"):
        totals[key] = int(totals.get(key, 0) or 0)
    totals["cost_usd"] = float(totals.get("cost_usd", 0.0) or 0.0)
    if not isinstance(data["days"], dict):
        data["days"] = {}
    return data


def save(data: dict) -> Path:
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        SPEND_FILE.parent.mkdir(parents=True, exist_ok=True)
        SPEND_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except OSError:
        pass
    return SPEND_FILE


def today_key() -> str:
    return time.strftime("%Y-%m-%d")


def month_key(day: str | None = None) -> str:
    return (day or today_key())[:7]


def day_usage(data: dict | None = None, day: str | None = None) -> dict:
    data = data if data is not None else load()
    entry = (data.get("days") or {}).get(day or today_key()) or {}
    return {"requests": int(entry.get("requests", 0) or 0),
            "prompt_tokens": int(entry.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(entry.get("completion_tokens", 0) or 0),
            "cost_usd": float(entry.get("cost_usd", 0.0) or 0.0)}


def month_usage(data: dict | None = None, month: str | None = None) -> dict:
    data = data if data is not None else load()
    prefix = month or month_key()
    total = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "cost_usd": 0.0}
    for day, entry in (data.get("days") or {}).items():
        if not str(day).startswith(prefix):
            continue
        for key in total:
            total[key] += type(total[key])(entry.get(key, 0) or 0)
    return total


# --------------------------------------------------------------------------
# Настройки: лимиты и цены (лежат рядом с ключом — в api_key.json)
# --------------------------------------------------------------------------
def settings_path() -> Path:
    """Тот же файл, что у ключа: иначе человек не поймёт, что где править."""
    import config

    custom = os.getenv("POWERMILL_API_KEY_FILE")
    if custom:
        return Path(custom)
    return Path(config.DATA_ROOT) / "api_key.json"


def read_file_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def limits(settings: dict | None = None) -> dict:
    """Лимиты: значения по умолчанию, перекрытые файлом и переменными окружения."""
    file_data = read_file_settings()
    source = dict(settings or {})
    values = dict(DEFAULT_LIMITS)
    for key, default in DEFAULT_LIMITS.items():
        raw = (source.get(key) if source.get(key) is not None
               else file_data.get(key))
        if raw is None:
            continue
        try:
            values[key] = type(default)(raw)
        except (TypeError, ValueError):
            continue
    env_map = {
        "LLM_DAILY_REQUESTS": "daily_requests",
        "LLM_DAILY_COST_USD": "daily_cost_usd",
        "LLM_MONTHLY_COST_USD": "monthly_cost_usd",
        "LLM_MAX_TOKENS": "max_tokens_per_request",
    }
    for env_name, key in env_map.items():
        raw = os.getenv(env_name)
        if raw:
            try:
                values[key] = type(DEFAULT_LIMITS[key])(raw)
            except (TypeError, ValueError):
                continue
    return values


def prices(settings: dict | None = None) -> tuple[float, float, bool]:
    """Цены (вход, выход) за 1 млн токенов и признак «известны ли они».

    Порядок: файл → пресет провайдера. Если нигде нет — 0 и «неизвестно»:
    тогда считаем токены, а деньги не выдумываем.
    """
    file_data = read_file_settings()
    source = dict(settings or {})
    provider = (source.get("provider") or file_data.get("provider") or "").lower()

    raw_in = source.get("price_input_per_m")
    raw_out = source.get("price_output_per_m")
    if raw_in is None:
        raw_in = file_data.get("price_input_per_m")
    if raw_out is None:
        raw_out = file_data.get("price_output_per_m")
    try:
        price_in = float(raw_in) if raw_in not in (None, "") else None
        price_out = float(raw_out) if raw_out not in (None, "") else None
    except (TypeError, ValueError):
        price_in = price_out = None

    if price_in is None or price_out is None:
        preset_in, preset_out = PRICES.get(provider, (0.0, 0.0))
        price_in = preset_in if price_in is None else price_in
        price_out = preset_out if price_out is None else price_out
    known = bool(price_in or price_out)
    return float(price_in), float(price_out), known


def update_limits(values: dict, extra: dict | None = None) -> Path:
    """Пишет лимиты (и, если надо, цены) в тот же файл, где ключ. Ключ не трогает."""
    path = settings_path()
    data = read_file_settings()
    for key, value in values.items():
        if value is None:
            continue
        data[key] = value
    if extra:
        data.update({key: value for key, value in extra.items()
                     if value is not None})
    data["limits_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass
    return path


# --------------------------------------------------------------------------
# Цена запроса и запись расхода
# --------------------------------------------------------------------------
def estimate_cost(prompt_tokens: int, completion_tokens: int,
                  settings: dict | None = None) -> tuple[float, bool]:
    """Сколько примерно стоил запрос (доллары) и знаем ли мы цены."""
    price_in, price_out, known = prices(settings)
    cost = (prompt_tokens / 1_000_000 * price_in +
            completion_tokens / 1_000_000 * price_out)
    return round(cost, 6), known


def record(settings: dict | None = None, usage: dict | None = None,
           model: str = "") -> dict:
    """Записывает расход одного запроса. Возвращает то, что добавилось."""
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens")
                            or usage.get("output_tokens") or 0)
    if not prompt_tokens and not completion_tokens:
        total = int(usage.get("total_tokens") or 0)
        prompt_tokens = total          # хоть что-то: часть сервисов даёт только total
    cost, known = estimate_cost(prompt_tokens, completion_tokens, settings)
    if not known:
        cost = 0.0                     # цены не знаем — деньги не выдумываем

    data = load()
    day = today_key()
    entry = data["days"].setdefault(day, {"requests": 0, "prompt_tokens": 0,
                                          "completion_tokens": 0, "cost_usd": 0.0})
    entry["requests"] = int(entry.get("requests", 0)) + 1
    entry["prompt_tokens"] = int(entry.get("prompt_tokens", 0)) + prompt_tokens
    entry["completion_tokens"] = int(entry.get("completion_tokens", 0)) + completion_tokens
    entry["cost_usd"] = round(float(entry.get("cost_usd", 0.0)) + cost, 6)
    if model:
        entry["last_model"] = model

    totals = data["totals"]
    totals["requests"] = int(totals.get("requests", 0)) + 1
    totals["prompt_tokens"] = int(totals.get("prompt_tokens", 0)) + prompt_tokens
    totals["completion_tokens"] = int(totals.get("completion_tokens", 0)) + completion_tokens
    totals["cost_usd"] = round(float(totals.get("cost_usd", 0.0)) + cost, 6)
    save(data)
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "cost_usd": cost, "prices_known": known}


# --------------------------------------------------------------------------
# Проверка перед запросом
# --------------------------------------------------------------------------
def cap_tokens(requested: int, settings: dict | None = None) -> int:
    """Не даём запросить больше, чем разрешено лимитом."""
    limit = int(limits(settings).get("max_tokens_per_request", 0) or 0)
    if limit <= 0:
        return requested
    return max(1, min(int(requested), limit))


def check(settings: dict | None = None) -> tuple[bool, str]:
    """Можно ли делать запрос. (False, объяснение) — если лимит исчерпан."""
    limits_now = limits(settings)
    data = load()
    day = day_usage(data)
    month = month_usage(data)
    limit_requests = int(limits_now.get("daily_requests", 0) or 0)
    limit_day_cost = float(limits_now.get("daily_cost_usd", 0) or 0)
    limit_month_cost = float(limits_now.get("monthly_cost_usd", 0) or 0)
    price_in, price_out, known = prices(settings)

    if limit_requests and day["requests"] >= limit_requests:
        return False, _refusal(
            f"на сегодня уже {day['requests']} запросов — упёрлись в лимит "
            f"{limit_requests}",
            day, month, limits_now, known)
    if known and limit_day_cost and day["cost_usd"] >= limit_day_cost:
        return False, _refusal(
            f"за сегодня потрачено ${day['cost_usd']:.4f} — это лимит "
            f"${limit_day_cost:.2f} в день",
            day, month, limits_now, known)
    if known and limit_month_cost and month["cost_usd"] >= limit_month_cost:
        return False, _refusal(
            f"за месяц потрачено ${month['cost_usd']:.4f} — это лимит "
            f"${limit_month_cost:.2f} в месяц",
            day, month, limits_now, known)
    return True, ""


def _refusal(reason: str, day: dict, month: dict, limits_now: dict,
             prices_known: bool) -> str:
    lines = [
        "🛑 Лимит расходов на ИИ исчерпан — запрос к платному сервису НЕ отправлен.",
        f"   Причина: {reason}.",
        "",
        f"   Сегодня: {day['requests']} запросов, "
        f"{day['prompt_tokens']}+{day['completion_tokens']} токенов"
        + (f", ${day['cost_usd']:.4f}" if prices_known else ""),
        f"   За месяц: {month['requests']} запросов"
        + (f", ${month['cost_usd']:.4f}" if prices_known else ""),
        "",
        "Что делать:",
        "  • продолжить бесплатно: пункт 22 меню — переключиться на локальную "
        "модель (Ollama);",
        "  • поднять лимит: пункт 46 меню — расходы и лимиты;",
        "  • посмотреть, на что ушло: тот же пункт 46 (отчёт "
        "output\\api_spend_report.txt).",
    ]
    if not prices_known:
        lines.insert(6, "   (цены провайдера не заданы — считаю только токены, "
                        "лимиты по деньгам не проверяю)")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Что показать человеку
# --------------------------------------------------------------------------
def _money(value: float, known: bool) -> str:
    return f"${value:.4f}" if known else "цена не задана"


def summary_lines(settings: dict | None = None) -> list[str]:
    """Строки для /stats, окна, доктора и MCP: сколько потрачено и какой лимит."""
    data = load()
    day = day_usage(data)
    month = month_usage(data)
    totals = data["totals"]
    limits_now = limits(settings)
    _price_in, _price_out, known = prices(settings)
    provider = ""
    try:
        from src import llm

        current = llm.load_settings()
        provider = current.get("provider") or ""
        if current.get("backend") != "api":
            provider = ""
    except Exception:                                         # noqa: BLE001
        pass
    lines = [f"Расходы на ИИ (облачный API) — {SPEND_FILE}"]
    if provider:
        lines.append(f"  провайдер: {provider}")
    lines += [
        f"  сегодня: {day['requests']} запросов, "
        f"{day['prompt_tokens']}+{day['completion_tokens']} токенов, "
        f"{_money(day['cost_usd'], known)}",
        f"  за месяц: {month['requests']} запросов, "
        f"{month['prompt_tokens']}+{month['completion_tokens']} токенов, "
        f"{_money(month['cost_usd'], known)}",
        f"  всего: {totals['requests']} запросов, "
        f"{_money(totals['cost_usd'], known)}",
        f"  лимиты: {int(limits_now['daily_requests'])} запросов/день, "
        f"${limits_now['daily_cost_usd']:.2f}/день, "
        f"${limits_now['monthly_cost_usd']:.2f}/месяц, "
        f"не больше {int(limits_now['max_tokens_per_request'])} токенов на ответ",
    ]
    if not known:
        lines.append("  (!) цены провайдера не заданы: считаю только токены. "
                     "Задать: пункт 46 меню.")
    left = int(limits_now["daily_requests"]) - day["requests"]
    if left <= 0:
        lines.append("  (!) лимит запросов на сегодня исчерпан — запросы не уйдут, "
                     "пока не поднимешь лимит (пункт 46) или не сменишь на "
                     "локальную модель (пункт 22).")
    elif left <= max(1, int(limits_now["daily_requests"]) // 5):
        lines.append(f"  (!) осталось {left} запросов на сегодня.")
    return lines


def report_lines(settings: dict | None = None) -> list[str]:
    """Подробный отчёт: по дням за месяц + лимиты. Его можно прислать в чат."""
    data = load()
    limits_now = limits(settings)
    price_in, price_out, known = prices(settings)
    lines = [
        "=" * 62,
        "  РАСХОДЫ НА ОБЛАЧНЫЙ ИИ И ЛИМИТЫ (пункт 46)",
        "=" * 62,
        f"  Собрано: {time.strftime('%d.%m.%Y %H:%M')}",
        f"  Счётчики: {SPEND_FILE}",
        f"  Лимиты и цены: {settings_path()}",
        "",
        f"  Цены (за 1 млн токенов): вход ${price_in:.2f}, выход ${price_out:.2f}"
        + ("" if known else "  — НЕ ЗАДАНЫ, деньги не оценены"),
        "",
        "По дням (текущий месяц):",
    ]
    days = sorted((data.get("days") or {}).items(), reverse=True)
    month = month_key()
    shown = [(day, entry) for day, entry in days if day.startswith(month)]
    if not shown:
        lines.append("  пока пусто — запросов к платному сервису не было")
    for day, entry in shown[:31]:
        line = (f"  {day}: {int(entry.get('requests', 0))} запросов, "
                f"{int(entry.get('prompt_tokens', 0))}+"
                f"{int(entry.get('completion_tokens', 0))} токенов")
        if known:
            line += f", ${float(entry.get('cost_usd', 0.0)):.4f}"
        if entry.get("last_model"):
            line += f" (последняя модель: {entry['last_model']})"
        lines.append(line)

    totals = data["totals"]
    lines += [
        "",
        "Итого:",
        f"  всего с начала учёта: {totals['requests']} запросов, "
        f"{totals['prompt_tokens']}+{totals['completion_tokens']} токенов"
        + (f", ${totals['cost_usd']:.4f}" if known else ""),
        "",
        "Лимиты:",
        f"  запросов в день:        {int(limits_now['daily_requests'])}",
        f"  расход в день:          ${limits_now['daily_cost_usd']:.2f}",
        f"  расход в месяц:         ${limits_now['monthly_cost_usd']:.2f}",
        f"  токенов на один ответ:  {int(limits_now['max_tokens_per_request'])}",
        "",
        "Когда лимит исчерпан, запрос к платному сервису не уходит: приходит",
        "объяснение и подсказка переключиться на локальную модель (пункт 22).",
    ]
    return lines


def save_report(settings: dict | None = None) -> Path:
    text = "\n".join(report_lines(settings)) + "\n"
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return REPORT_FILE


def reset(settings: dict | None = None) -> Path:
    """Обнуляет счётчики (лимиты и ключ не трогает)."""
    data = _empty()
    data["totals"]["reset_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return save(data)

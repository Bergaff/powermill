"""
Тесты расходов на облачный ИИ и лимитов (пункт 46).

Главное, что проверяется: без денег мы не «забываем» про лимит. Запрос сверх
лимита не уходит в сеть, расходы считаются по токенам, лимиты не теряются при
повторном вводе ключа, а цены не выдумываются, если провайдер их не задал.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src import api_budget, llm

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def budget_files(tmp_path, monkeypatch):
    """Свои файлы настроек и счётчиков: чужие расходы в тестах не считаем."""
    key_file = tmp_path / "api_key.json"
    spend_file = tmp_path / "api_spend.json"
    monkeypatch.setattr(api_budget, "SPEND_FILE", spend_file)
    monkeypatch.setattr(api_budget, "REPORT_FILE", tmp_path / "output" /
                        "api_spend_report.txt")
    monkeypatch.setattr(api_budget, "settings_path", lambda: key_file)
    monkeypatch.setattr(llm, "API_KEY_FILE", key_file)
    # переменные окружения из системы не должны влиять на тесты
    for name in ("LLM_DAILY_REQUESTS", "LLM_DAILY_COST_USD",
                 "LLM_MONTHLY_COST_USD", "LLM_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    return key_file, spend_file


def write_settings(path: Path, **values) -> dict:
    data = {"provider": "deepseek", "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat", "api_key": "sk-test", "backend": "api"}
    data.update(values)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# --------------------------------------------------------------------------
# Учёт расходов
# --------------------------------------------------------------------------
def test_no_spend_file_means_no_spend(budget_files):
    usage = api_budget.day_usage()
    assert usage["requests"] == 0 and usage["cost_usd"] == 0.0


def test_record_counts_requests_tokens_and_money(budget_files):
    write_settings(budget_files[0])
    added = api_budget.record({"provider": "deepseek"},
                              {"prompt_tokens": 1000, "completion_tokens": 500},
                              model="deepseek-chat")
    # цены DeepSeek — примерные: 0.27 за вход и 1.10 за выход (за 1 млн токенов)
    assert added["prices_known"] is True
    assert added["cost_usd"] == pytest.approx(1000 / 1e6 * 0.27 + 500 / 1e6 * 1.10)
    usage = api_budget.day_usage()
    assert usage["requests"] == 1
    assert usage["prompt_tokens"] == 1000
    assert usage["completion_tokens"] == 500
    assert api_budget.load()["totals"]["requests"] == 1


def test_record_keeps_days_separate(budget_files):
    write_settings(budget_files[0])
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 100})
    data = api_budget.load()
    data["days"]["2026-01-05"] = {"requests": 7, "prompt_tokens": 70,
                                  "completion_tokens": 0, "cost_usd": 0.01}
    api_budget.save(data)
    # день и месяц считаются из «дней», поэтому чужая дата видна только там
    assert api_budget.day_usage()["requests"] == 1          # сегодня — своё
    assert api_budget.month_usage(month="2026-01")["requests"] == 7
    assert api_budget.load()["totals"]["requests"] == 1     # итог — счётчик запросов


def test_unknown_prices_count_tokens_only(budget_files):
    write_settings(budget_files[0], provider="custom", price_input_per_m="",
                   price_output_per_m="")
    added = api_budget.record({"provider": "custom"},
                              {"prompt_tokens": 5000, "completion_tokens": 1000})
    assert added["prices_known"] is False
    assert added["cost_usd"] == 0.0                        # деньги не выдумываем
    assert api_budget.day_usage()["prompt_tokens"] == 5000
    text = "\n".join(api_budget.summary_lines())
    assert "цены провайдера не заданы" in text


def test_own_prices_from_the_key_file(budget_files):
    write_settings(budget_files[0], price_input_per_m=1.0, price_output_per_m=2.0)
    added = api_budget.record({"provider": "deepseek"},
                              {"prompt_tokens": 1_000_000,
                               "completion_tokens": 1_000_000})
    assert added["cost_usd"] == pytest.approx(3.0)


def test_broken_spend_file_does_not_break_anything(budget_files):
    budget_files[1].write_text("{это не json", encoding="utf-8")
    assert api_budget.day_usage()["requests"] == 0
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 10})
    assert api_budget.day_usage()["requests"] == 1


# --------------------------------------------------------------------------
# Лимиты: мягкие по умолчанию, правятся снаружи
# --------------------------------------------------------------------------
def test_default_limits_are_safe(budget_files):
    limits = api_budget.limits()
    assert limits["daily_requests"] > 0
    assert 0 < limits["daily_cost_usd"] <= 1
    assert 0 < limits["monthly_cost_usd"] <= 10
    assert limits["max_tokens_per_request"] <= 4096


def test_limits_can_be_changed_in_the_file_and_by_env(budget_files, monkeypatch):
    write_settings(budget_files[0], daily_requests=7, monthly_cost_usd=1.5)
    limits = api_budget.limits()
    assert limits["daily_requests"] == 7 and limits["monthly_cost_usd"] == 1.5
    monkeypatch.setenv("LLM_DAILY_REQUESTS", "3")
    assert api_budget.limits()["daily_requests"] == 3       # окружение важнее файла


def test_update_limits_keeps_the_key(budget_files):
    write_settings(budget_files[0])
    api_budget.update_limits({"daily_requests": 12, "daily_cost_usd": 0.25},
                             {"price_input_per_m": 0.3})
    data = json.loads(budget_files[0].read_text(encoding="utf-8"))
    assert data["api_key"] == "sk-test"                    # ключ цел
    assert data["model"] == "deepseek-chat"
    assert data["daily_requests"] == 12
    assert data["price_input_per_m"] == 0.3


def test_cap_tokens_respects_the_limit(budget_files):
    write_settings(budget_files[0], max_tokens_per_request=256)
    assert api_budget.cap_tokens(2048) == 256
    assert api_budget.cap_tokens(100) == 100
    write_settings(budget_files[0], max_tokens_per_request=0)
    assert api_budget.cap_tokens(2048) == 2048             # 0 = без ограничения


# --------------------------------------------------------------------------
# Главное: лимит останавливает запрос ДО обращения к сервису
# --------------------------------------------------------------------------
def test_request_limit_blocks_with_a_clear_message(budget_files):
    write_settings(budget_files[0], daily_requests=2)
    for _ in range(2):
        api_budget.record({"provider": "deepseek"}, {"prompt_tokens": 10})
    allowed, message = api_budget.check()
    assert allowed is False
    assert "НЕ отправлен" in message
    assert "пункт 22" in message          # куда идти за бесплатным продолжением
    assert "пункт 46" in message          # где поднять лимит


def test_money_limit_blocks(budget_files):
    write_settings(budget_files[0], daily_requests=1000, daily_cost_usd=0.01)
    api_budget.record({"provider": "deepseek"},
                      {"prompt_tokens": 100_000, "completion_tokens": 10_000})
    allowed, message = api_budget.check()
    assert allowed is False
    assert "лимит" in message and "$" in message


def test_monthly_limit_blocks_even_when_today_is_quiet(budget_files):
    write_settings(budget_files[0], daily_requests=1000,
                   monthly_cost_usd=0.001)
    data = api_budget.load()
    data["days"][api_budget.month_key() + "-01"] = {
        "requests": 3, "prompt_tokens": 100_000, "completion_tokens": 5000,
        "cost_usd": 0.05}
    api_budget.save(data)
    allowed, message = api_budget.check()
    assert allowed is False
    assert "месяц" in message


def test_money_limits_do_not_block_when_prices_unknown(budget_files):
    """Если цены провайдера не заданы, лимит по деньгам не выдумываем."""
    write_settings(budget_files[0], provider="custom", daily_requests=1000,
                   price_input_per_m="", price_output_per_m="",
                   daily_cost_usd=0.0001)
    api_budget.record({"provider": "custom"}, {"total_tokens": 1_000_000})
    allowed, _message = api_budget.check()
    assert allowed is True


def test_chat_refuses_without_touching_the_network(budget_files, monkeypatch):
    """Самое важное: сверх лимита запрос в сеть НЕ уходит."""
    settings = write_settings(budget_files[0], daily_requests=1)
    api_budget.record(settings, {"prompt_tokens": 10})

    def forbidden(*_args, **_kwargs):
        raise AssertionError("запрос ушёл в сеть, хотя лимит исчерпан")

    monkeypatch.setattr(llm.urllib.request, "urlopen", forbidden)
    answer = llm.chat("вопрос", settings=settings)
    assert "Лимит расходов" in answer
    assert "пункт 46" in answer


def test_chat_records_usage_from_the_answer(budget_files, monkeypatch):
    settings = write_settings(budget_files[0])
    body = json.dumps({
        "choices": [{"message": {"content": "Готово"}}],
        "usage": {"prompt_tokens": 1234, "completion_tokens": 56},
    }).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return body

    def fake_urlopen(_request, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    answer = llm.chat("вопрос", settings=settings, max_tokens=64)
    assert answer == "Готово"
    usage = api_budget.day_usage()
    assert usage["requests"] == 1
    assert usage["prompt_tokens"] == 1234 and usage["completion_tokens"] == 56


def test_chat_shortens_the_requested_answer_to_the_limit(budget_files, monkeypatch):
    settings = write_settings(budget_files[0], max_tokens_per_request=100)
    seen: dict = {}

    def fake_urlopen(request, timeout=None):
        seen.update(json.loads(request.data.decode("utf-8")))
        raise llm.urllib.error.URLError("дальше не важно")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    llm.chat("вопрос", settings=settings, max_tokens=4096)
    assert seen["max_tokens"] == 100


# --------------------------------------------------------------------------
# Настройки ключа и лимитов не мешают друг другу
# --------------------------------------------------------------------------
def test_saving_the_key_again_keeps_limits(budget_files):
    """Повторный пункт 21 не должен стирать поставленные лимиты."""
    path = budget_files[0]
    write_settings(path, daily_requests=11, monthly_cost_usd=2.5,
                   price_input_per_m=0.3)
    llm.save_settings("deepseek", "https://api.deepseek.com/v1", "deepseek-chat",
                      "sk-new")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["api_key"] == "sk-new"
    assert data["daily_requests"] == 11
    assert data["monthly_cost_usd"] == 2.5
    assert data["price_input_per_m"] == 0.3


def test_report_shows_days_and_limits(budget_files):
    write_settings(budget_files[0])
    api_budget.record({"provider": "deepseek"},
                      {"prompt_tokens": 2000, "completion_tokens": 800})
    path = api_budget.save_report()
    text = path.read_text(encoding="utf-8")
    assert "РАСХОДЫ НА ОБЛАЧНЫЙ ИИ И ЛИМИТЫ" in text
    assert "По дням" in text
    assert api_budget.today_key() in text
    assert "Лимиты:" in text


def test_reset_clears_counters_only(budget_files):
    write_settings(budget_files[0], daily_requests=9)
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 100})
    api_budget.reset()
    assert api_budget.day_usage()["requests"] == 0
    assert api_budget.limits()["daily_requests"] == 9
    assert "sk-test" in budget_files[0].read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Пункт 46 в меню, скрипт и батник
# --------------------------------------------------------------------------
def test_script_show_and_set_by_keys(budget_files, capfd):
    """capfd, а не capsys: скрипты печатают через src/applog._Tee в свой stdout."""
    from scripts import api_budget as script

    write_settings(budget_files[0])
    assert script.main(["--show"]) == 0
    assert "РАСХОДЫ НА ИИ И ЛИМИТЫ" in capfd.readouterr().out

    assert script.main(["--limit-requests", "25", "--limit-daily-usd", "0.4",
                        "--max-tokens", "1500"]) == 0
    limits = api_budget.limits()
    assert limits["daily_requests"] == 25
    assert limits["daily_cost_usd"] == pytest.approx(0.4)
    assert limits["max_tokens_per_request"] == 1500
    assert "sk-test" in budget_files[0].read_text(encoding="utf-8")


def test_script_report_and_reset(budget_files, capfd):
    from scripts import api_budget as script

    write_settings(budget_files[0])
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 100})
    assert script.main(["--report"]) == 0
    assert "api_spend_report.txt" in capfd.readouterr().out
    assert script.main(["--reset", "--yes"]) == 0
    assert api_budget.day_usage()["requests"] == 0


def test_script_interactive_set_from_input(budget_files, monkeypatch, capfd):
    """Диалог: Enter — оставить, число — поменять."""
    from scripts import api_budget as script

    write_settings(budget_files[0])
    answers = iter(["40", "0.25", "", "1024"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers, ""))
    assert script.main(["--set"]) == 0
    limits = api_budget.limits()
    assert limits["daily_requests"] == 40
    assert limits["daily_cost_usd"] == pytest.approx(0.25)
    assert limits["monthly_cost_usd"] == 5.0             # Enter — как было
    assert limits["max_tokens_per_request"] == 1024


def test_menu_has_point_46():
    text = (PROJECT_ROOT / "start_menu.bat").read_text(encoding="utf-8",
                                                       errors="replace")
    assert "Выбор (0-48)" in text
    assert "46  -  Расходы на ИИ и лимиты" in text
    assert ':spend' in text
    assert 'if "%choice%"=="46" goto spend' in text
    assert "scripts\\api_budget.bat" in text


def test_bat_is_double_clickable_and_mentions_limits():
    text = (PROJECT_ROOT / "scripts" / "api_budget.bat").read_text(
        encoding="utf-8", errors="replace")
    assert "chcp 65001" in text
    assert ".venv\\Scripts\\python.exe" in text and "venv\\Scripts\\python.exe" in text
    assert "--set" in text
    assert "пункт 22" in text                    # куда идти за бесплатным ИИ
    assert "api_spend_report.txt" in text


def test_window_button_and_doctor_see_the_spend(budget_files):
    from src import app_window, doctor, pm_buttons

    action = pm_buttons.by_key("spend")
    assert action is not None and action.group == pm_buttons.GROUP_SETUP
    assert [plan.title for plan in app_window.plans()
            if plan.action.key == "spend"]
    write_settings(budget_files[0], daily_requests=1)
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 10})
    check = doctor.check_api_budget()
    assert "46" in check.title
    assert check.status == doctor.STATUS_WARN          # лимит исчерпан — предупреждаем
    assert "пункт 22" in check.advice


def test_stats_in_chat_show_spend(budget_files, monkeypatch, capsys):
    from src import rag
    from src.retrieval import NullVectorStore

    write_settings(budget_files[0])
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 10})
    monkeypatch.setattr("src.llm.load_settings", llm.load_settings)
    ai = rag.PowerMillAI(store=NullVectorStore(), load_fts=False, verbose=False)
    text = ai.stats()
    assert "Расходы на ИИ" in text
    assert "лимиты:" in text


def test_mcp_has_the_spend_tool(budget_files, monkeypatch):
    from src import mcp_server

    write_settings(budget_files[0])
    api_budget.record({"provider": "deepseek"}, {"total_tokens": 10})
    names = [tool.name for tool in mcp_server.build_tools()]
    assert "powermill_ai_spend" in names
    text = mcp_server.tool_ai_spend()
    assert "Расходы на ИИ" in text
    assert "пунктом 46" in text                 # где менять лимиты

"""Тесты облачного ИИ по API (src/llm.py).

Проверяем на поддельном сервере, который повторяет OpenAI-совместимый
`/v1/chat/completions`: успешный ответ, неверный ключ, лимит запросов,
недоступный сервер и разбор ответов с ошибками. Интернет для тестов не нужен.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


# --------------------------------------------------------------------------
# Поддельный сервис
# --------------------------------------------------------------------------
class FakeAPI(BaseHTTPRequestHandler):
    # настройки задаются тестом через атрибуты класса
    mode = "ok"
    last_request: dict = {}
    answer = "Готово, модель fake-1"

    def do_POST(self) -> None:  # noqa: N802 — так требует http.server
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            FakeAPI.last_request = json.loads(body)
        except json.JSONDecodeError:
            FakeAPI.last_request = {}
        FakeAPI.last_request["_auth"] = self.headers.get("Authorization", "")

        if FakeAPI.mode == "unauthorized":
            self.send_response(401)
            payload = {"error": {"message": "Incorrect API key provided"}}
        elif FakeAPI.mode == "rate_limit":
            self.send_response(429)
            payload = {"error": {"message": "Rate limit reached"}}
        elif FakeAPI.mode == "server_error":
            self.send_response(500)
            payload = {"error": {"message": "internal"}}
        elif FakeAPI.mode == "not_json":
            self.send_response(200)
            data = b"<html>oops</html>"
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        elif FakeAPI.mode == "weird":
            self.send_response(200)
            payload = {"unexpected": True}
        else:
            self.send_response(200)
            payload = {"choices": [{"message": {"content": FakeAPI.answer}}]}

        data = json.dumps(payload).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:      # тишина в тестах
        pass


@pytest.fixture
def api_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    FakeAPI.mode = "ok"
    FakeAPI.last_request = {}
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


@pytest.fixture
def settings(api_server):
    from src import llm

    return {
        "backend": "api", "provider": "custom", "base_url": api_server,
        "model": "fake-1", "code_model": "fake-1", "api_key": "test-key",
        "timeout": 10.0, "temperature": 0.2, "source": "тест",
    }


# --------------------------------------------------------------------------
# Успешные сценарии
# --------------------------------------------------------------------------
def test_successful_answer(settings):
    from src import llm

    assert llm.chat("вопрос", settings=settings) == FakeAPI.answer


def test_request_contains_key_model_and_prompt(settings):
    from src import llm

    llm.chat("проверка промпта", settings=settings, system="ты технолог")
    request = FakeAPI.last_request
    assert request["_auth"] == "Bearer test-key"
    assert request["model"] == "fake-1"
    roles = [m["role"] for m in request["messages"]]
    assert roles == ["system", "user"]
    assert request["messages"][-1]["content"] == "проверка промпта"
    assert request["stream"] is False


def test_model_can_be_overridden(settings):
    from src import llm

    llm.chat("вопрос", model="другая-модель", settings=settings)
    assert FakeAPI.last_request["model"] == "другая-модель"


# --------------------------------------------------------------------------
# Ошибки: понятные сообщения по-русски
# --------------------------------------------------------------------------
def test_bad_key_message(settings):
    from src import llm

    FakeAPI.mode = "unauthorized"
    answer = llm.chat("вопрос", settings=settings)
    assert "401" in answer
    assert "пункт 21" in answer          # подсказка, что делать


def test_rate_limit_message(settings):
    from src import llm

    FakeAPI.mode = "rate_limit"
    answer = llm.chat("вопрос", settings=settings)
    assert "429" in answer
    assert "лимит" in answer.lower()


def test_server_error_message(settings):
    from src import llm

    FakeAPI.mode = "server_error"
    answer = llm.chat("вопрос", settings=settings)
    assert "500" in answer


def test_not_json_answer(settings):
    from src import llm

    FakeAPI.mode = "not_json"
    answer = llm.chat("вопрос", settings=settings)
    assert answer.startswith("❌")
    assert "не JSON" in answer


def test_weird_answer(settings):
    from src import llm

    FakeAPI.mode = "weird"
    answer = llm.chat("вопрос", settings=settings)
    assert answer.startswith("❌")


def test_no_connection_returns_message():
    from src import llm

    settings = {"backend": "api", "provider": "custom",
                "base_url": "http://127.0.0.1:9/v1", "model": "fake",
                "api_key": "k", "timeout": 3.0, "source": "тест"}
    answer = llm.chat("вопрос", settings=settings)
    assert answer.startswith("❌")
    assert "связи" in answer.lower()


def test_missing_key_is_explained():
    from src import llm

    settings = {"backend": "api", "provider": "custom", "base_url": "http://x/v1",
                "model": "m", "api_key": "", "timeout": 3.0, "source": "тест"}
    answer = llm.chat("вопрос", settings=settings)
    assert "нет ключа" in answer.lower()
    assert "пункт 21" in answer


def test_missing_base_url_is_explained():
    from src import llm

    settings = {"backend": "api", "provider": "custom", "base_url": "",
                "model": "m", "api_key": "k", "timeout": 3.0, "source": "тест"}
    answer = llm.chat("вопрос", settings=settings)
    assert "нет адреса" in answer.lower()


# --------------------------------------------------------------------------
# Настройки: файл, окружение, режимы
# --------------------------------------------------------------------------
def test_save_and_load_settings(tmp_path, monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "API_KEY_FILE", tmp_path / "api_key.json")
    for var in ("LLM_PROVIDER", "LLM_API_BASE", "LLM_API_MODEL", "LLM_API_KEY",
                "LLM_BACKEND"):
        monkeypatch.delenv(var, raising=False)

    llm.save_settings("deepseek", "https://api.deepseek.com/v1", "deepseek-chat",
                      "secret-key")
    loaded = llm.load_settings()
    assert loaded["backend"] == "api"
    assert loaded["model"] == "deepseek-chat"
    assert loaded["base_url"] == "https://api.deepseek.com/v1"

    # ключ не должен быть виден целиком в описании
    described = llm.describe_settings(loaded)
    assert "secret-key" not in described
    assert described.count("•") or described.endswith("-key")


def test_auto_backend_without_key_is_local(tmp_path, monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "API_KEY_FILE", tmp_path / "нет.json")
    for var in ("LLM_PROVIDER", "LLM_API_BASE", "LLM_API_MODEL", "LLM_API_KEY",
                "LLM_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    assert llm.load_settings()["backend"] == "local"


def test_env_overrides_file(tmp_path, monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "API_KEY_FILE", tmp_path / "api_key.json")
    llm.save_settings("openai", "https://api.openai.com/v1", "gpt-4o-mini", "key1")
    monkeypatch.setenv("LLM_API_MODEL", "другая")
    assert llm.load_settings()["model"] == "другая"


def test_local_backend_uses_local_models(tmp_path, monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "API_KEY_FILE", tmp_path / "нет.json")
    for var in ("LLM_PROVIDER", "LLM_API_BASE", "LLM_API_MODEL", "LLM_API_KEY",
                "LLM_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    settings = llm.load_settings()
    assert llm.pick_model("chat", settings)
    assert llm.pick_model("code", settings)


def test_providers_have_hints():
    from src import llm

    for key, info in llm.PROVIDERS.items():
        assert info["title"], key
        assert info["how"], key
    assert set(llm.PROVIDERS) >= {"openai", "openrouter", "deepseek", "groq",
                                  "ollama", "custom"}


# --------------------------------------------------------------------------
# Проверка подключения
# --------------------------------------------------------------------------
def test_connection_ok(settings, capsys):
    from src import llm

    assert llm.test_connection(settings) == 0
    assert "OK" in capsys.readouterr().out


def test_connection_fails_on_bad_key(settings, capsys):
    from src import llm

    FakeAPI.mode = "unauthorized"
    assert llm.test_connection(settings) == 2
    out = capsys.readouterr().out
    assert "НЕ РАБОТАЕТ" in out
    assert "пункт 21" in out


# --------------------------------------------------------------------------
# Чат: команды /ask и /macro уходят в API, когда он настроен
# --------------------------------------------------------------------------
def test_chat_uses_api_when_configured(settings, monkeypatch):
    from src import llm, rag

    monkeypatch.setattr(llm, "load_settings", lambda: settings)
    ai = rag.PowerMillAI(store=object(), load_fts=False, verbose=False)
    monkeypatch.setattr(rag.PowerMillAI, "_retrieve", lambda self, q, top_k=None: [])

    answer = ai.ask("Как задать припуск на границе?")
    assert FakeAPI.answer in answer
    assert FakeAPI.last_request["model"] == "fake-1"


def test_macro_goes_to_api_with_vocabulary(settings, monkeypatch):
    from src import llm, rag

    monkeypatch.setattr(llm, "load_settings", lambda: settings)
    ai = rag.PowerMillAI(store=object(), load_fts=False, verbose=False)
    monkeypatch.setattr(rag.PowerMillAI, "_retrieve", lambda self, q, top_k=None: [])
    FakeAPI.answer = "```pml\n// пример\nPRINT \"готово\"\n```"

    out = ai.macro("проверка", save=False)
    assert "PRINT" in out
    # в промпт ушли и выдержки, и словарь проверенных имён
    prompt = FakeAPI.last_request["messages"][-1]["content"]
    assert "ПРОВЕРЕННЫЕ ИМЕНА" in prompt
    FakeAPI.answer = "Готово, модель fake-1"

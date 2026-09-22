"""
RAG-ассистент по PowerMill: поиск в ChromaDB + генерация ответа через Ollama.

Режимы:
  * обычный вопрос  -> модель LLM_MODEL (qwen2.5:3b)
  * /macro <задача> -> модель LLM_CODE_MODEL (qwen2.5-coder:3b)
"""
import ollama

from config import (
    CURRENT_MODE,
    LLM_CODE_MODEL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    TOP_K,
)
from src.hardware import set_process_priority
from src.vectorstore import PowerMillVectorStore

SYSTEM_PROMPT_CHAT = """Ты — опытный инженер-технолог ЧПУ и эксперт по Autodesk PowerMill.
Отвечай точно, кратко и по делу на русском языке.
Правила:
- Используй точную терминологию PowerMill
- Давай конкретные пошаговые действия, не общие слова
- Если не уверен — скажи об этом, не выдумывай
- Ссылайся на источники из контекста

Контекст из базы знаний:
{context}
"""

SYSTEM_PROMPT_MACRO = """Ты — эксперт по макроязыку PML для Autodesk PowerMill.
Генерируй ТОЛЬКО рабочий PML-код с комментариями на русском.

Синтаксис PML:
- Переменные: $var = "value", $var = 123
- Условия: IF $var == "x" { ... } ELSE { ... }
- Циклы: FOREACH $item IN $list { ... }
- Комментарии: // комментарий

Полезные фрагменты из базы знаний:
{context}
"""


class PowerMillAI:
    def __init__(self):
        set_process_priority(CURRENT_MODE)
        self.store = PowerMillVectorStore()

    def ask(self, query: str, is_macro: bool = False) -> str:
        hits = self.store.search(query, top_k=TOP_K)
        context = "\n---\n".join(h["text"] for h in hits)

        if is_macro:
            model = LLM_CODE_MODEL
            prompt = SYSTEM_PROMPT_MACRO.format(context=context)
            temperature = 0.3
        else:
            model = LLM_MODEL
            prompt = SYSTEM_PROMPT_CHAT.format(context=context)
            temperature = 0.5

        full_prompt = f"{prompt}\n\nВопрос технолога: {query}\n\nОтвет эксперта:"

        try:
            response = ollama.generate(
                model=model,
                prompt=full_prompt,
                keep_alive=OLLAMA_KEEP_ALIVE,  # eco: 0s — сразу освобождаем VRAM
                options={"temperature": temperature, "num_predict": 2048},
            )
            answer = response["response"]
        except Exception as e:
            return (
                f"❌ Ошибка Ollama: {e}\n"
                f"Проверь, что Ollama запущена и модель {model} загружена "
                f"(ollama pull {model})."
            )

        if not is_macro and hits:
            sources = sorted({h["source"] for h in hits})
            answer += f"\n\n📚 Источники: {', '.join(sources)}"
        return answer


def run_chat():
    ai = PowerMillAI()
    print("\n" + "=" * 60)
    print(" 🤖 PowerMill AI Assistant готов к работе!")
    print(" Команды: вопрос текстом | /macro <задача> | /exit")
    print("=" * 60)

    while True:
        try:
            q = input("\n👨‍💻 Технолог: ").strip()
            if not q:
                continue
            if q.lower() in {"/exit", "exit", "quit", "/q"}:
                print("👋 До свидания!")
                break

            is_macro = q.startswith("/macro")
            if is_macro:
                q = q[len("/macro"):].strip()
                if not q:
                    print("⚠️ Укажи задачу: /macro создать границы по всем отверстиям")
                    continue

            print("\n🤖 ИИ думает...")
            answer = ai.ask(q, is_macro=is_macro)
            print(f"\n💡 Ответ:\n{answer}")

        except KeyboardInterrupt:
            print("\n👋 До свидания!")
            break


if __name__ == "__main__":
    run_chat()

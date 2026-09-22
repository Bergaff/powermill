"""
RAG-ассистент по PowerMill: поиск в ChromaDB + генерация ответа через Ollama.

Режимы:
  * обычный вопрос  -> модель LLM_MODEL (qwen2.5:3b)
  * /macro <задача>  -> модель LLM_CODE_MODEL (qwen2.5-coder:3b)
  * /sources         -> показать найденные фрагменты без генерации (отладка)
"""
import ollama

from config import (
    CURRENT_MODE,
    LLM_CODE_MODEL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    SOURCE_MAX_DISTANCE,
    TOP_K,
)
from src.hardware import set_process_priority
from src.vectorstore import PowerMillVectorStore

SYSTEM_PROMPT_CHAT = """Ты — инженер-технолог ЧПУ, эксперт по Autodesk PowerMill.

Жёсткие правила:
1. Отвечай ТОЛЬКО по контексту из базы знаний ниже.
2. Если в контексте нет ответа на вопрос — прямо напиши:
   "В документации по этому вопросу ничего не нашёл" и предложи,
   какое слово/термин поискать. НИЧЕГО не выдумывай.
3. Не смешивай разные темы. Если вопрос про стратегию обработки —
   говори про стратегию обработки, не про рабочие плоскости и станки.
4. Отвечай на русском, кратко и по шагам, только по делу.
5. Не добавляй общие слова вроде "может варьироваться в зависимости
   от конфигурации", если это не вытекает из контекста.

Контекст из базы знаний PowerMill:
{context}
"""

SYSTEM_PROMPT_MACRO = """Ты — эксперт по макроязыку PML для Autodesk PowerMill.
Генерируй ТОЛЬКО рабочий PML-код с комментариями на русском.
Если в контексте нет примеров — всё равно пиши код по своему
знанию синтаксиса PML, но пометь ответ: "// сгенерировано без опоры на документацию".

Синтаксис PML:
- Переменные: $var = "value", $var = 123
- Условия: IF $var == "x" { ... } ELSE { ... }
- Циклы: FOREACH $item IN $list { ... }
- Комментарии: // комментарий

Полезные фрагменты из базы знаний:
{context}
"""


def _format_hits(hits: list[dict]) -> str:
    """Склеивает найденные фрагменты в контекст для промпта."""
    if not hits:
        return "(пусто — релевантных фрагментов не найдено)"
    parts = []
    for h in hits:
        parts.append(f"[источник: {h['source']}, релевантность: {h['distance']:.2f}]\n{h['text']}")
    return "\n---\n".join(parts)


def _format_sources(hits: list[dict]) -> str:
    if not hits:
        return "📚 Источники: не найдено (ни один фрагмент не прошёл фильтр релевантности)"
    return "📚 Источники: " + ", ".join(
        f"{h['source']} ({h['distance']:.2f})" for h in hits
    )


class PowerMillAI:
    def __init__(self):
        set_process_priority(CURRENT_MODE)
        self.store = PowerMillVectorStore()

    def search_debug(self, query: str) -> list[dict]:
        """Возвращает сырые hits из базы (для команды /sources)."""
        return self.store.search(query, top_k=max(TOP_K, 6))

    def ask(self, query: str, is_macro: bool = False) -> str:
        raw_hits = self.store.search(query, top_k=max(TOP_K, 4))

        # Фильтр релевантности: отсекаем явно не по теме фрагменты.
        # У cosine distance меньше = лучше; 0.0 — точное совпадение.
        hits = [h for h in raw_hits if h["distance"] <= SOURCE_MAX_DISTANCE]

        context = _format_hits(hits)

        if is_macro:
            model = LLM_CODE_MODEL
            prompt = SYSTEM_PROMPT_MACRO.format(context=context)
            temperature = 0.3
        else:
            model = LLM_MODEL
            prompt = SYSTEM_PROMPT_CHAT.format(context=context)
            temperature = 0.2  # ниже = меньше выдумок

        full_prompt = f"{prompt}\n\nВопрос технолога: {query}\n\nОтвет эксперта:"

        try:
            response = ollama.generate(
                model=model,
                prompt=full_prompt,
                keep_alive=OLLAMA_KEEP_ALIVE,  # eco: 0s — сразу освобождаем VRAM
                options={
                    "temperature": temperature,
                    "num_predict": 2048,
                    "num_ctx": 4096,
                },
            )
            answer = response["response"]
        except Exception as e:
            return (
                f"❌ Ошибка Ollama: {e}\n"
                f"Проверь, что Ollama запущена и модель {model} загружена "
                f"(ollama pull {model})."
            )

        if not is_macro:
            answer += "\n\n" + _format_sources(hits)
        return answer


def _print_search_results(query: str, ai: PowerMillAI) -> None:
    hits = ai.search_debug(query)
    if not hits:
        print("(база пуста — сначала прогони start_night_indexing.bat)")
        return
    print(f"Найдено для: {query!r}")
    print(f"Порог релевантности: {SOURCE_MAX_DISTANCE} "
          f"(меньше = точнее), TOP_K={TOP_K}\n")
    for i, h in enumerate(hits, 1):
        passed = "OK " if h["distance"] <= SOURCE_MAX_DISTANCE else "SKIP"
        preview = h["text"][:200].replace("\n", " ")
        print(f"  {i}. [{passed}] dist={h['distance']:.3f}  source={h['source']}")
        print(f"     {preview}...\n")
    passed = [h for h in hits if h["distance"] <= SOURCE_MAX_DISTANCE]
    print(f"Прошли фильтр: {len(passed)} из {len(hits)}")


def run_chat():
    ai = PowerMillAI()
    print("\n" + "=" * 60)
    print(" 🤖 PowerMill AI Assistant готов к работе!")
    print(" Команды:")
    print("   <текст вопроса>   — вопрос по документации")
    print("   /macro <задача>   — генерация PML-макроса")
    print("   /sources <вопрос> — показать найденные фрагменты")
    print("   /exit             — выход")
    print("=" * 60)

    while True:
        try:
            q = input("\n👨‍💻 Технолог: ").strip()
            if not q:
                continue
            if q.lower() in {"/exit", "exit", "quit", "/q"}:
                print("👋 До свидания!")
                break

            if q.startswith("/sources"):
                rest = q[len("/sources"):].strip()
                if not rest:
                    print("⚠️ Использование: /sources как сделать границу")
                    continue
                print()
                _print_search_results(rest, ai)
                continue

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

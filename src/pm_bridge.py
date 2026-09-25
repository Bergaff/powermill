"""
Мост «PowerMill ↔ ассистент» через файлы (шаг 2.2 без плагина).

Как это работает
----------------
1. Внутри PowerMill технолог запускает макрос `PM_AI_ASK.mac`.
2. Макрос спрашивает режим и текст, пишет их в `output\\pm_request.txt` и
   запускает `pm_answer.bat` (стандартной командой PML `OLE FILEACTION`).
3. Этот модуль читает запрос, отправляет его туда же, куда команды чата
   (`/ask`, `/macro`, `/error`, `/cutting`), и пишет ответ в
   `output\\pm_answer.txt`.
4. Макрос читает файл и показывает ответ в окне PowerMill.

Ответ пишется в файл сразу («ассистент думает…»), чтобы макрос никогда не
натыкался на отсутствующий файл.
"""
from __future__ import annotations

from src import pml_files

import json
import time
from pathlib import Path

from config import OUTPUT_DIR
from src.pm_macro import ANSWER_FILE, MODES, REQUEST_FILE


def mode_code(index: int) -> str:
    """Номер пункта меню из макроса -> код режима."""
    try:
        number = int(index)
    except (TypeError, ValueError):
        return "ask"
    if 0 <= number < len(MODES):
        return MODES[number][0]
    return "ask"


def parse_request(text: str) -> dict:
    """Разбирает файл запроса от макроса.

    Формат (пишет макрос): первая строка `MODE=<номер>`, дальше текст запроса.
    Дополнительно понимаем `MODE=ask` — на случай ручной правки файла.
    """
    lines = (text or "").replace("\r\n", "\n").split("\n")
    mode = "ask"
    rest: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        # строку режима узнаём по «MODE=»; иначе даже первая строка — это запрос
        if stripped.upper().startswith("MODE="):
            value = stripped.split("=", 1)[-1].strip()
            if value.isdigit():
                mode = mode_code(int(value))
                continue
            lowered = value.lower()
            matched = next((code for code, _title in MODES if lowered == code), "")
            if matched:
                mode = matched
                continue
            rest.append(line)
            continue
        if index == 0 and stripped and not stripped.upper().startswith("MODE"):
            rest.append(line)
            continue
        rest.append(line)

    query = "\n".join(rest).strip()
    return {"mode": mode, "query": query}


def write_answer(text: str, path: Path | None = None) -> Path:
    """Пишет ответ для макроса (в кодировке, которую прочитает PML)."""
    target = Path(path or ANSWER_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    # PowerMill читает файл в системной кодировке — пишем CP1251,
    # иначе русский ответ в окне PowerMill выглядит как «РѕС‚РІРµС‚»
    pml_files.write(target, text)
    return target


def write_placeholder(path: Path | None = None) -> Path:
    """Заглушка «думаю» — чтобы макрос всегда нашёл файл."""
    return write_answer(
        "Ассистент готовит ответ…\n\n"
        "Когда в отдельном окне появится надпись «Ответ готов»,\n"
        "нажми RESUME в PowerMill — ответ появится здесь.",
        path)


def clean_for_power_mill(text: str, limit: int = 4000) -> str:
    """Готовит текст для окна PowerMill: без markdown-мусора и лишней длины."""
    cleaned = (text or "")
    for token in ("```pml", "```python", "```"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.replace("**", "").replace("##", "")
    cleaned = cleaned.strip()
    if len(cleaned) > limit:
        cleaned = cleaned[:limit] + "\n…(продолжение — в файле ответа)"
    return cleaned


def answer_request(query: str, mode: str, ai=None, progress=None) -> str:
    """Считает ответ тем же движком, что и чат.

    Режимы резания считаются формулами — им не нужны ни ИИ, ни векторная база,
    поэтому они обрабатываются раньше и работают всегда.

    `progress` — необязательная функция для интерфейса (пункт 32): через неё
    уходят понятные шаги, чтобы технолог видел, что происходит, а не пустой экран.
    """
    report = progress or (lambda _text: None)

    def note(text: str) -> None:
        try:
            report(text)
        except Exception:                                  # noqa: BLE001
            pass

    if mode == "cutting":
        note("Считаю режимы резания по формулам (без ИИ и без базы)…")
        from src import cutting

        answer = cutting.answer(query)[0]
        note("Расчёт готов")
        return answer

    note("Поднимаю ассистента: справка + словарь PML + векторная база…")
    from src.rag import PowerMillAI

    if ai is None:
        ai = PowerMillAI(verbose=bool(progress))

    if mode == "macro":
        note("Собираю словарь настоящего PML и пишу макрос…")
        return ai.macro(query, save=True)
    if mode == "error":
        note("Ищу похожие ошибки в справке…")
        return ai.error(query)
    note("Ищу в справке и формулирую ответ…")
    return ai.ask(query)


def handle(path: Path | None = None, ai=None, verbose: bool = True) -> int:
    """Полный цикл: запрос из файла -> ответ в файл. Код 0 — успех."""
    request_path = Path(path or REQUEST_FILE)
    if not request_path.exists():
        print(f"(!) Нет файла запроса {request_path}")
        print("    Запрос создаёт макрос PM_AI_ASK.mac внутри PowerMill.")
        return 2

    raw = pml_files.read(request_path)
    request = parse_request(raw)
    if not request["query"] or request["query"] == "(пустой запрос)":
        write_answer("Пустой запрос.\n\nЗапусти макрос PM_AI_ASK.mac заново "
                     "и введи текст вопроса.")
        print("(!) Пустой запрос")
        return 3

    # сразу пишем заглушку — макрос не должен ждать пустого файла
    write_placeholder()

    started = time.time()
    if verbose:
        print("=" * 58)
        print(f"  ЗАПРОС ИЗ PowerMill ({request['mode']})")
        print("=" * 58)
        print(request["query"])
        print()
        print("Думаю…")

    try:
        answer = answer_request(request["query"], request["mode"], ai=ai)
    except ImportError as error:
        answer = ("❌ Не хватает библиотек для ответов ИИ: "
                  f"{error}\n\nЗапусти пункт 18 меню (быстрая установка) — "
                  "он поставит нужное за минуту.\n"
                  "Режимы резания (пункт 3 меню и режим «Режимы резания» "
                  "в макросе) работают и без ИИ.")
        write_answer(clean_for_power_mill(answer))
        print(answer)
        return 5
    except Exception as error:  # noqa: BLE001 — мост не должен падать
        answer = (f"❌ Не удалось подготовить ответ: {type(error).__name__}: {error}\n"
                  f"Подробности — в output\\logs\\ (пункт 19 меню).")
        write_answer(clean_for_power_mill(answer))
        print(answer)
        return 4

    seconds = time.time() - started
    header = (f"PowerMill AI · режим: {request['mode']} · "
              f"{seconds:.0f} с\n" + "-" * 50 + "\n")
    text = clean_for_power_mill(header + answer)
    write_answer(text)

    if verbose:
        print()
        print(text)
        print()
        print(f"[Ответ готов] {ANSWER_FILE}")
    return 0


def main() -> int:
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else None
    return handle(path)


if __name__ == "__main__":
    import sys

    sys.exit(main())

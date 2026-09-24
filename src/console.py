"""
Общая логика консольных экранов: возврат «назад» и возврат в меню.

Зачем отдельный модуль: и калькулятор режимов, и поиск по справке, и чат
должны одинаково понимать слова-команды:

    назад / back / -        вернуться на шаг назад (или в меню)
    меню / menu / выход / q  вернуться в главное меню (start_menu.bat)
    ? / help / справка       показать подсказку

Класс Wizard — пошаговый опрос с возвратом на предыдущий шаг:
технолог может ошибиться на третьем вопросе и вернуться на второй,
не начиная всё заново.
"""
from __future__ import annotations

BACK_WORDS = {"назад", "back", "<", "-", "н", "b"}
MENU_WORDS = {"меню", "menu", "m", "выход", "exit", "quit", "q", "й"}
HELP_WORDS = {"?", "help", "h", "справка", "помощь"}
SKIP_WORDS = {"", "далее", "next", "ок", "ok", "пропустить", "skip"}


def classify(text: str) -> str:
    """Строка пользователя -> 'back' | 'menu' | 'help' | 'skip' | 'input'."""
    t = (text or "").strip().lower()
    if t in BACK_WORDS:
        return "back"
    if t in MENU_WORDS:
        return "menu"
    if t in HELP_WORDS:
        return "help"
    if t in SKIP_WORDS:
        return "skip"
    return "input"


class Wizard:
    """Пошаговый опрос с возможностью вернуться на шаг назад.

    steps — список кортежей (заголовок, подсказка, значение по умолчанию).
    """

    def __init__(self, steps: list[tuple[str, str, str]], answers: list[str] | None = None):
        self.steps = steps
        self.answers = list(answers or [""] * len(steps))
        while len(self.answers) < len(steps):
            self.answers.append("")
        self.index = 0

    # ---------------- состояние ----------------
    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def finished(self) -> bool:
        return self.index >= self.total

    def current(self) -> tuple[str, str, str]:
        """(заголовок, подсказка, текущее значение по умолчанию)."""
        title, hint, default = self.steps[self.index]
        previous = self.answers[self.index]
        return title, hint, previous or default

    def prompt(self) -> str:
        title, hint, default = self.current()
        text = f"[{self.index + 1}/{self.total}] {title}"
        if hint:
            text += f" ({hint})"
        if default:
            text += f" [Enter = {default}]"
        return text + ": "

    def values(self) -> list[str]:
        """Заполненные ответы (для сборки запроса)."""
        return [a.strip() for a in self.answers if a and a.strip()]

    def query(self, fallback: str = "") -> str:
        return ", ".join(self.values()) or fallback

    # ---------------- ввод ----------------
    def submit(self, text: str) -> str:
        """Обрабатывает ответ и возвращает действие:

        'next'  — приняли, переходим к следующему шагу
        'done'  — все шаги пройдены, можно считать
        'back'  — вернулись на шаг назад
        'menu'  — выход в главное меню
        'help'  — показать подсказку
        """
        action = classify(text)

        if action == "menu":
            return "menu"
        if action == "help":
            return "help"
        if action == "back":
            if self.index == 0:
                return "menu"          # назад с первого шага = в меню
            self.index -= 1
            return "back"

        if action == "skip":
            _, _, default = self.current()
            self.answers[self.index] = default
        else:
            self.answers[self.index] = text.strip()

        self.index += 1
        return "done" if self.finished else "next"

    def restart(self) -> None:
        """Начать заново, сохранив прежние ответы как значения по умолчанию."""
        self.index = 0


def read_line(prompt: str) -> str | None:
    """input() без падения на Ctrl+C / закрытом вводе. None = выход."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None

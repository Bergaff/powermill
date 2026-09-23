"""
Telegram-бот PowerMill AI (aiogram 3).

Запуск: python -m src.bot   (нужен TELEGRAM_BOT_TOKEN в .env или окружении)
Команды: /start — приветствие, любой текст — вопрос, /macro <задача> — PML-макрос.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import TELEGRAM_BOT_TOKEN
from src.rag import PowerMillAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()
ai: PowerMillAI | None = None


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🤖 <b>PowerMill AI Assistant</b>\n\n"
        "Просто напиши вопрос по PowerMill — отвечу по документации.\n"
        "Для генерации PML-макроса: <code>/macro опиши задачу</code>\n"
        "Выход: <code>/exit</code>",
        parse_mode="HTML",
    )


@dp.message(Command("exit"))
async def cmd_exit(message: Message) -> None:
    await message.answer("👋 Пока! Приходи снова.")


@dp.message(F.text & ~Command("macro"))
async def handle_question(message: Message) -> None:
    query = (message.text or "").strip()
    if not query:
        return
    status = await message.answer("🤖 ИИ думает...")
    answer = await asyncio.to_thread(ai.ask, query, False)
    await status.edit_text(answer[:4096])


@dp.message(Command("macro"))
async def handle_macro(message: Message) -> None:
    query = (message.text or "")[len("/macro"):].strip()
    if not query:
        await message.answer("⚠️ Укажи задачу: /macro создать границы по всем отверстиям")
        return
    status = await message.answer("⚙️ Генерирую PML-макрос...")
    answer = await asyncio.to_thread(ai.ask, query, True)
    await status.edit_text(answer[:4096])


async def main() -> None:
    global ai
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "❌ Задай TELEGRAM_BOT_TOKEN в файле .env или в переменных окружения."
        )
    ai = PowerMillAI()  # загружает эмбеддинги; chroma_db на диске E
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    print("🤖 Telegram-бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

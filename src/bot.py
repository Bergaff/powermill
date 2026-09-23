"""
Telegram-бот PowerMill AI (aiogram 3).

Запуск: python -m src.bot   (нужен TELEGRAM_BOT_TOKEN в .env или окружении)

Команды (те же, что в консольном чате):
  /start, /help            — справка
  любой текст              — вопрос по документации
  /ask <вопрос>            — то же явно
  /macro <задача>          — генерация PML-макроса (файл сохраняется на диск E)
  /cutting <материал> <фреза> — режимы резания S/F/ap/ae
  /error <текст ошибки>    — причина + что исправить
  /compare <A> и <B>       — таблица сравнения
  /stats                   — состав базы знаний
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import TELEGRAM_BOT_TOKEN
from src.rag import PowerMillAI, split_compare

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()
ai: PowerMillAI | None = None

HELLO = (
    "🤖 <b>PowerMill AI Assistant</b>\n\n"
    "Просто напиши вопрос по PowerMill — отвечу по документации.\n\n"
    "Команды:\n"
    "• <code>/ask вопрос</code> — вопрос по справке\n"
    "• <code>/macro задача</code> — PML-макрос\n"
    "• <code>/cutting Сталь 40Х фреза D16 черновая</code> — режимы резания\n"
    "• <code>/error текст ошибки</code> — разбор ошибки\n"
    "• <code>/compare A и B</code> — сравнить две стратегии\n"
    "• <code>/stats</code> — что в базе знаний"
)
MAX_LEN = 4000


async def send_long(message: Message, text: str) -> None:
    """Telegram режет сообщения на 4096 символов — отправляем частями."""
    text = text or "(пусто)"
    for i in range(0, len(text), MAX_LEN):
        await message.answer(text[i:i + MAX_LEN])


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELLO, parse_mode="HTML")


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELLO, parse_mode="HTML")


@dp.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    await send_long(message, await asyncio.to_thread(ai.stats))


@dp.message(Command("cutting"))
async def cmd_cutting(message: Message) -> None:
    query = (message.text or "")[len("/cutting"):].strip()
    if not query:
        await message.answer("⚠️ Пример: <code>/cutting Сталь 40Х, фреза D16, черновая</code>",
                             parse_mode="HTML")
        return
    await send_long(message, await asyncio.to_thread(ai.cutting_answer, query))


@dp.message(Command("macro"))
async def cmd_macro(message: Message) -> None:
    task = (message.text or "")[len("/macro"):].strip()
    if not task:
        await message.answer("⚠️ Пример: <code>/macro создать границы по всем отверстиям</code>",
                             parse_mode="HTML")
        return
    status = await message.answer("⚙️ Генерирую PML-макрос...")
    answer = await asyncio.to_thread(ai.macro, task)
    await status.delete()
    await send_long(message, answer)


@dp.message(Command("error"))
async def cmd_error(message: Message) -> None:
    text = (message.text or "")[len("/error"):].strip()
    if not text:
        await message.answer("⚠️ Пример: <code>/error Toolpath calculation failed - undercut</code>",
                             parse_mode="HTML")
        return
    status = await message.answer("🔧 Разбираю ошибку...")
    answer = await asyncio.to_thread(ai.error, text)
    await status.delete()
    await send_long(message, answer)


@dp.message(Command("compare"))
async def cmd_compare(message: Message) -> None:
    text = (message.text or "")[len("/compare"):].strip()
    if not text:
        await message.answer("⚠️ Пример: <code>/compare Model Area Clearance и Offset Area</code>",
                             parse_mode="HTML")
        return
    status = await message.answer("⚖️ Сравниваю...")
    answer = await asyncio.to_thread(ai.compare, text)
    await status.delete()
    await send_long(message, answer)


@dp.message(Command("ask"))
async def cmd_ask(message: Message) -> None:
    query = (message.text or "")[len("/ask"):].strip()
    if not query:
        await message.answer("⚠️ Пример: <code>/ask как сделать чистовую по кривой</code>",
                             parse_mode="HTML")
        return
    status = await message.answer("🤖 Ищу в документации...")
    answer = await asyncio.to_thread(ai.ask, query)
    await status.delete()
    await send_long(message, answer)


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_question(message: Message) -> None:
    query = (message.text or "").strip()
    if not query:
        return
    # «Чем A отличается от B» в свободной форме — сразу на сравнение
    if split_compare(query)[1] and query.lower().startswith(("чем", "сравни", "что лучше")):
        status = await message.answer("⚖️ Сравниваю...")
        answer = await asyncio.to_thread(ai.compare, query)
        await status.delete()
        await send_long(message, answer)
        return
    status = await message.answer("🤖 Ищу в документации...")
    answer = await asyncio.to_thread(ai.ask, query)
    await status.delete()
    await send_long(message, answer)


async def main() -> None:
    global ai
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "❌ Задай TELEGRAM_BOT_TOKEN в файле .env или в переменных окружения."
        )
    ai = PowerMillAI()  # загружает эмбеддинги и keyword-индекс; chroma_db на диске E
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    print("🤖 Telegram-бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

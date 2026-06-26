import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from openai import AsyncOpenAI
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "ВАШ_КЛЮЧ_СЮДА")
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))
BOT_USERNAME = "arsi"
MODEL = "deepseek-chat"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# ✅ Исправлен base_url - убран /v1 на конце
openai_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

chat_history = []
large_context = ""

if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл загружен: {len(large_context)} симв.")
else:
    logging.critical(f"Файл '{FILE_NAME}' не найден!")
    sys.exit(1)


async def ask_deepseek(user_text: str) -> str:
    global chat_history

    chat_history.append({"role": "user", "content": user_text})

    system_instruction = (
        f"Ты полезный ассистент. Отвечай строго по загруженному тексту:\n\n{large_context}"
    )

    messages = [{"role": "system", "content": system_instruction}] + chat_history

    try:
        response = await openai_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=False
        )

        reply = response.choices[0].message.content

        chat_history.append({"role": "assistant", "content": reply})

        if len(chat_history) > 20:
            chat_history = chat_history[-20:]

        return reply

    except Exception as e:
        logging.error(f"Ошибка API DeepSeek: {e}")
        if chat_history and chat_history[-1]["content"] == user_text:
            chat_history.pop()
        raise e


async def handle_message(message: Message, text: str):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        reply = await ask_deepseek(text)
        await message.reply(reply)
    except Exception as e:
        await message.reply(f"Произошла ошибка при обращении к DeepSeek: {e}")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        f"Привет! База данных загружена под DeepSeek.\n"
        "В группе: /arsi ваш вопрос\n"
        "Проверка: /status"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    await message.answer(
        f"✅ Бот работает на модели `{MODEL}`\n"
        f"Размер системного контекста: {len(large_context)} симв.\n"
        f"Сообщений в текущей истории: {len(chat_history)}",
        parse_mode="Markdown"
    )


@dp.message(Command("arsi"))
async def cmd_arsi(message: Message):
    text = message.text.replace("/arsi", "", 1).strip()
    if text.startswith(f"@{BOT_USERNAME}"):
        text = text[len(f"@{BOT_USERNAME}"):].strip()
    if not text:
        await message.reply("Напишите вопрос: /arsi ваш вопрос")
        return
    await handle_message(message, text)


@dp.message(F.chat.type == "private")
async def private_message(message: Message):
    if not message.text:
        return
    await handle_message(message, message.text.strip())


async def handle_hc(request):
    return web.Response(text="Бот онлайн!")


async def main():
    app = web.Application()
    app.router.add_get('/', handle_hc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {PORT}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

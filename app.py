import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from google import genai
from google.genai import errors
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = "8843575311:AAHAc5994cnfJwbXUfMFdagENlRvIi2hye0"
GEMINI_API_KEY = "AQ.Ab8RN6JIz59H2TAUEE8JsoFk-SHv3M4IGRYFpRFIBYlbYFIwLQ"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Хранилище сессий: {user_id: {"chat": chat, "prompt_loaded": bool}}
user_sessions = {}
large_context = ""

if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл '{FILE_NAME}' загружен ({len(large_context)} симв.)")
else:
    logging.critical(f"Файл '{FILE_NAME}' не найден!")
    sys.exit(1)


def create_chat():
    """Создаёт новый чат без промта"""
    return gemini_client.chats.create(
        model="gemini-2.5-flash",
        config={"system_instruction": "Ты полезный ассистент."}
    )


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    user_id = message.from_user.id
    user_sessions[user_id] = {
        "chat": create_chat(),
        "prompt_loaded": False
    }
    await message.answer(
        "Привет! Сессия создана.\n\n"
        "Чтобы загрузить базу данных в контекст — напишите *Загрузи промт*\n"
        "Или просто задавайте вопросы без базы данных.",
        parse_mode="Markdown"
    )


@dp.message()
async def message_handler(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()

    # Создаём сессию если нет (например бот перезапустился)
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "chat": create_chat(),
            "prompt_loaded": False
        }

    session = user_sessions[user_id]

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Команда загрузки промта
    if user_text.lower() == "загрузи промт":
        if session["prompt_loaded"]:
            await message.answer("База данных уже загружена в эту сессию.")
            return

        await message.answer("Загружаю базу данных...")
        try:
            await asyncio.to_thread(
                session["chat"].send_message,
                f"Прочитай и запомни этот текст. Ниже будут вопросы:\n\n{large_context}"
            )
            session["prompt_loaded"] = True
            await message.answer("✅ База данных загружена! Задавайте вопросы.")
        except errors.APIError as e:
            logging.error(f"Ошибка загрузки промта для {user_id}: {e}")
            await message.answer(f"Ошибка при загрузке: {e}")
        return

    # Обычное сообщение
    try:
        response = await asyncio.to_thread(session["chat"].send_message, user_text)
        await message.answer(response.text)
    except errors.APIError as e:
        logging.error(f"Gemini API Error для {user_id}: {e}")
        await message.answer(f"Ошибка со стороны ИИ: {e}")
    except Exception as e:
        logging.error(f"Ошибка для {user_id}: {e}")
        await message.answer(f"Не удалось получить ответ: {e}")


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

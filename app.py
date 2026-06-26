import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
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

large_context = ""
if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл '{FILE_NAME}' загружен ({len(large_context)} симв.)")
else:
    logging.critical(f"Файл '{FILE_NAME}' не найден!")
    sys.exit(1)

# Одна глобальная сессия для всех
global_chat = None
prompt_loaded = False


def create_chat():
    return gemini_client.chats.create(
        model="gemini-2.5-flash",
        config={"system_instruction": "Ты полезный ассистент."}
    )


async def load_prompt(message: types.Message):
    """Отправляет промт в глобальный чат"""
    global prompt_loaded
    await message.answer("Загружаю базу данных...")
    try:
        await asyncio.to_thread(
            global_chat.send_message,
            f"Прочитай и запомни этот текст. Ниже будут вопросы:\n\n{large_context}"
        )
        prompt_loaded = True
        logging.info("Промт успешно загружен в глобальную сессию")
        await message.answer("✅ База данных загружена!")
    except errors.APIError as e:
        logging.error(f"Ошибка загрузки промта: {e}")
        await message.answer(f"Ошибка при загрузке: {e}")


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    global global_chat, prompt_loaded

    if global_chat is None:
        # Первый /start — создаём сессию и грузим промт
        global_chat = create_chat()
        await load_prompt(message)
    else:
        await message.answer(
            "Сессия уже активна, база данных загружена.\n"
            "Задавайте вопросы! Чтобы перезагрузить базу — напишите *Загрузи промт*",
            parse_mode="Markdown"
        )


@dp.message()
async def message_handler(message: types.Message):
    global global_chat, prompt_loaded
    user_text = message.text.strip()

    # Если сессии ещё нет (бот перезапустился)
    if global_chat is None:
        global_chat = create_chat()
        prompt_loaded = False

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Команда перезагрузки промта
    if user_text.lower() == "загрузи промт":
        prompt_loaded = False  # сбрасываем флаг чтобы загрузить заново
        await load_prompt(message)
        return

    # Обычное сообщение
    try:
        response = await asyncio.to_thread(global_chat.send_message, user_text)
        await message.answer(response.text)
    except errors.APIError as e:
        logging.error(f"Gemini API Error: {e}")
        await message.answer(f"Ошибка со стороны ИИ: {e}")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer(f"Не удалось получить ответ: {e}")


async def handle_hc(request):
    return web.Response(text="Бот онлайн!")


async def main():
    global global_chat
    # Создаём сессию сразу при старте бота
    global_chat = create_chat()
    logging.info("Глобальная сессия Gemini создана")

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

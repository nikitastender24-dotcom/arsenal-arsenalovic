import asyncio
import logging
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai
from google.genai import errors
from aiohttp import web

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

KEY_FILE = "key.json"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))

# 1. Читаем ключи из key.json
if os.path.exists(KEY_FILE):
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            keys_data = json.load(f)
        TELEGRAM_BOT_TOKEN = keys_data.get("TELEGRAM_BOT_TOKEN")
        GEMINI_API_KEY = keys_data.get("GEMINI_API_KEY")
        logging.info("Ключи из key.json успешно загружены.")
    except Exception as e:
        logging.critical(f"Ошибка чтения файла key.json: {e}")
        exit(1)
else:
    logging.critical(f"Критическая ошибка: Файл '{KEY_FILE}' не найден!")
    exit(1)

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    logging.critical("Внутри key.json отсутствуют нужные ключи!")
    exit(1)

# Инициализация ИИ и Бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
user_chats = {}
large_context = ""

# 2. Читаем тяжелый текстовый файл
if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Контекст на {len(large_context)} символов загружен.")
else:
    logging.critical(f"Файл '{FILE_NAME}' не найден!")
    exit(1)

async def init_gemini_chat_for_user(user_id: int):
    chat = gemini_client.chats.create(
        model="gemini-3.5-flash",
        config={"system_instruction": "Ты полезный ассистент, отвечающий строго по предоставленному тексту."}
    )
    first_prompt = f"Прочитай и запомни этот текст. Ниже будут вопросы:\n\n{large_context}"
    await asyncio.to_thread(chat.send_message, first_prompt)
    user_chats[user_id] = chat

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    user_id = message.from_user.id
    await message.answer("Секунду... Загружаю базу данных (800 КБ текста) в вашу сессию ИИ...")
    try:
        await init_gemini_chat_for_user(user_id)
        await message.answer("Готово! Контекст загружен. Задавайте вопросы по файлу.")
    except Exception as e:
        logging.error(f"Ошибка ИИ для {user_id}: {e}")
        await message.answer("Ошибка при инициализации. Попробуйте снова: /start")

@dp.message()
async def message_handler(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_chats:
        await message.answer("Отправьте /start для инициализации файла.")
        return
    
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        chat = user_chats[user_id]
        response = await asyncio.to_thread(chat.send_message, message.text)
        await message.answer(response.text)
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        await message.answer("Не удалось получить ответ от ИИ.")

# Заглушка для проверки доступности (Healthcheck) от Railway
async def handle_hc(request):
    return web.Response(text="Бот активен и работает через key.json!")

async def main():
    # Стартуем веб-сервер для Railway
    app = web.Application()
    app.router.add_get('/', handle_hc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Фейковый веб-сервер запущен на порту {PORT}")

    # Стартуем ТГ бота
    logging.info("Поллинг Telegram бота запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

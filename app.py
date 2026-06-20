import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai
from google.genai import errors
# ИМПОРТИРУЕМ СПЕЦИАЛЬНЫЙ КЛАСС ДЛЯ КЛЮЧЕЙ "AQ..."
from google.genai.errors import APIError
from google.genai._api_key import APIKeyCredentials 
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ================= КЛЮЧИ И НАСТРОЙКИ =================
TELEGRAM_BOT_TOKEN = "8843575311:AAHAc5994cnfJwbXUfMFdagENlRvIi2hye0"
GEMINI_API_KEY = "AQ.Ab8RN6LNCGfezco-Om8crrq8yHaWqdVclOnKQJ8cZg2vkFXmJQ"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))
# =====================================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# ОФИЦИАЛЬНОЕ РЕШЕНИЕ ИЗ ФОРУМА РАЗРАБОТЧИКОВ GOOGLE:
# Обертываем наш ключ AQ... в специальный класс credentials,
# чтобы SDK не путал его с OAuth2 токеном Google Cloud.
credentials = APIKeyCredentials(api_key=GEMINI_API_KEY)
gemini_client = genai.Client(credentials=credentials)

user_chats = {}
large_context = ""

if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл '{FILE_NAME}' успешно загружен ({len(large_context)} симв.)")
else:
    logging.critical(f"Критическая ошибка: Файл '{FILE_NAME}' не найден!")
    sys.exit(1)


async def get_or_create_chat(user_id: int, message_to_alert: types.Message = None):
    if user_id in user_chats:
        return user_chats[user_id]
        
    logging.info(f"Инициализация сессии через APIKeyCredentials для {user_id}...")
    if message_to_alert:
        await message_to_alert.answer("Секунду... Загружаю базу данных в вашу сессию ИИ...")

    # Используем gemini-2.5-flash или gemini-1.5-flash (3.5-flash тоже поддерживается)
    chat = gemini_client.chats.create(
        model="gemini-1.5-flash",
        config={"system_instruction": "Ты полезный ассистент, отвечающий строго по предоставленному тексту."}
    )
    
    first_prompt = f"Прочитай и запомни этот текст. Ниже будут вопросы:\n\n{large_context}"
    await asyncio.to_thread(chat.send_message, first_prompt)
    user_chats[user_id] = chat
    return chat


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    user_id = message.from_user.id
    try:
        await get_or_create_chat(user_id, message_to_alert=message)
        await message.answer("Готово! База данных загружена по умолчанию. Задавайте ваши вопросы.")
    except Exception as e:
        logging.error(f"Ошибка при /start для {user_id}: {e}")
        await message.answer("Ошибка ИИ. Проверь логи, пробился ли ключ через Credentials.")


@dp.message()
async def message_handler(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        chat = await get_or_create_chat(user_id, message_to_alert=message)
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        response = await asyncio.to_thread(chat.send_message, user_text)
        await message.answer(response.text)
        
    except errors.APIError as e:
        logging.error(f"Gemini API Error для {user_id}: {e}")
        await message.answer("Ошибка со стороны ИИ.")
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения для {user_id}: {e}")
        await message.answer("Не удалось получить ответ.")


async def handle_hc(request):
    return web.Response(text="Бот онлайн, фикс ключей AQ через APIKeyCredentials применен!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_hc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {PORT}")
    logging.info("Поллинг Telegram бота запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

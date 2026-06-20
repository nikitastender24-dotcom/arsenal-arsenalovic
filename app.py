import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai
from google.genai import errors
from aiohttp import web

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ================= АКТУАЛЬНЫЕ КЛЮЧЕЙ =================
TELEGRAM_BOT_TOKEN = "8843575311:AAHAc5994cnfJwbXUfMFdagENlRvIi2hye0"
GEMINI_API_KEY = "AQ.Ab8RN6LNCGfezco-Om8crrq8yHaWqdVclOnKQJ8cZg2vkFXmJQ"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))
# =====================================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Инициализируем клиент с версией v1beta для стабильной работы по REST
gemini_client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

user_chats = {}
large_context = ""

# Читаем тяжелый текстовый файл
if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл '{FILE_NAME}' успешно загружен. Размер: {len(large_context)} символов.")
else:
    logging.critical(f"Критическая ошибка: Файл '{FILE_NAME}' не найден в репозитории!")
    exit(1)


async def get_or_create_chat(user_id: int, message_to_alert: types.Message = None):
    """Возвращает существующий чат или создает новый сеанс с загруженным промтом"""
    if user_id in user_chats:
        return user_chats[user_id]
        
    logging.info(f"Инициализация новой сессии для пользователя {user_id}...")
    
    if message_to_alert:
        await message_to_alert.answer("Секунду... Загружаю базу данных в вашу сессию ИИ...")

    # Используем проверенную модель gemini-1.5-flash
    chat = gemini_client.chats.create(
        model="gemini-1.5-flash",
        config={"system_instruction": "Ты полезный ассистент, отвечающий строго по предоставленному текста."}
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
        await message.answer("Не удалось запустить сессию ИИ. Проверь логи на Railway.")


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
        await message.answer("Ошибка со стороны ИИ. Возможно, файл слишком тяжелый или превышены лимиты.")
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения для {user_id}: {e}")
        await message.answer("Не удалось получить ответ.")


# Заглушка для проверки доступности (Healthcheck) от Railway
async def handle_hc(request):
    return web.Response(text="Бот онлайн, применен новый токен Telegram!")

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

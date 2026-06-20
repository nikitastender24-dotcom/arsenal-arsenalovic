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

# ================= ЖЕСТКО ВШИТЫЕ КЛЮЧИ =================
TELEGRAM_BOT_TOKEN = "8843575311:AAEJElYqN7OUH8HftqcILd8GEBvrnrALANY"
GEMINI_API_KEY = "AQ.Ab8RN6L5lv7yO0bAJeDARh7v6DnNG_pSjvh_ddxIr2qIBK-J6Q"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))
# =======================================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Инициализация ИИ Gemini с двойной авторизацией
gemini_client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"headers": {"X-goog-api-key": GEMINI_API_KEY}}
)

user_chats = {}
large_context = ""

# Читаем файл из репозитория при старте сервера
if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл '{FILE_NAME}' на {len(large_context)} символов успешно прочитан из репозитория.")
else:
    logging.critical(f"Критическая ошибка: Файл '{FILE_NAME}' не найден в корне проекта!")
    exit(1)


async def get_or_create_chat(user_id: int, message_to_alert: types.Message = None):
    """
    Возвращает существующий чат или создает новый, 
    автоматически загружая туда 700 КБ промта по умолчанию.
    """
    if user_id in user_chats:
        return user_chats[user_id]
        
    logging.info(f"Инициализация новой сессии для пользователя {user_id}...")
    
    # Если это первое сообщение, предупреждаем пользователя, так как загрузка 700 КБ занимает время
    if message_to_alert:
        await message_to_alert.answer("Секунду... Загружаю базу данных в вашу сессию ИИ...")

    chat = gemini_client.chats.create(
        model="gemini-3.5-flash",
        config={"system_instruction": "Ты полезный ассистент, отвечающий строго по предоставленному тексту."}
    )
    
    first_prompt = f"Прочитай и запомни этот текст. Ниже будут вопросы:\n\n{large_context}"
    
    # Скармливаем промт по умолчанию в фоне
    await asyncio.to_thread(chat.send_message, first_prompt)
    user_chats[user_id] = chat
    return chat


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    """При команде /start просто принудительно создаем сессию заранее"""
    user_id = message.from_user.id
    try:
        await get_or_create_chat(user_id, message_to_alert=message)
        await message.answer("Готово! База данных загружена по умолчанию. Задавайте ваши вопросы.")
    except Exception as e:
        logging.error(f"Ошибка при /start для {user_id}: {e}")
        await message.answer("Ошибка инициализации. Возможно, ваш API-ключ Gemini заблокирован.")


@dp.message()
async def message_handler(message: types.Message):
    """Обработка любых сообщений. Если сессии нет — она создастся на лету"""
    user_id = message.from_user.id
    user_text = message.text

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Автоматически получаем или создаем чат (промт зашлется по умолчанию, если его не было)
        chat = await get_or_create_chat(user_id, message_to_alert=message)
        
        # Показываем статус "печатает" повторно, так как инициализация могла занять время
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Отправляем текущий вопрос пользователя
        response = await asyncio.to_thread(chat.send_message, user_text)
        await message.answer(response.text)
        
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения для {user_id}: {e}")
        await message.answer("Не удалось получить ответ. Проверьте логи сервера или обновите API-ключ.")


# Заглушка для проверки доступности (Healthcheck) от Railway
async def handle_hc(request):
    return web.Response(text="Бот активен, промт по умолчанию загружен в память сервера!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_hc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Фейковый веб-сервер запущен на порту {PORT}")
    logging.info("Поллинг Telegram бота запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

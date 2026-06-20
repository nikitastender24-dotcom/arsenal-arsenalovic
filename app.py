import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai
from google.genai import errors

# Настройка логирования для отслеживания работы бота в панели Railway
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Получаем токены из переменных окружения Railway
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FILE_NAME = "large_prompt.txt"

# Проверка, что переменные окружения заданы
if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    logging.critical("Критические переменные окружения (TELEGRAM_BOT_TOKEN или GEMINI_API_KEY) не настроены!")
    exit(1)

# Инициализация клиентов
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Словарь для хранения сессий чата {user_id: chat_session}
user_chats = {}
large_context = ""

# Читаем файл при старте бота
if os.path.exists(FILE_NAME):
    try:
        with open(FILE_NAME, 'r', encoding='utf-8') as f:
            large_context = f.read()
        logging.info(f"Файл '{FILE_NAME}' успешно загружен. Размер: {len(large_context)} символов.")
    except Exception as e:
        logging.critical(f"Не удалось прочитать файл '{FILE_NAME}': {e}")
        exit(1)
else:
    logging.critical(f"Файл '{FILE_NAME}' отсутствует в корневой директории!")
    exit(1)


async def init_gemini_chat_for_user(user_id: int):
    """Создает индивидуальный чат в Gemini и загружает 800 КБ текста"""
    chat = gemini_client.chats.create(
        model="gemini-3.5-flash",
        config={
            "system_instruction": "Ты ассистент, который отвечает на любые вопросы пользователя строго на основе предоставленного текста."
        }
    )
    
    first_prompt = f"Прочитай и запомни этот текст. Ниже пользователь будет задавать по нему вопросы:\n\n{large_context}"
    
    # Отправляем тяжелый запрос в фоновом потоке, чтобы бот не блокировался
    await asyncio.to_thread(chat.send_message, first_prompt)
    user_chats[user_id] = chat


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} инициировал чат.")
    await message.answer("Секунду... Загружаю базу данных (800 КБ текста) в вашу сессию ИИ...")
    
    try:
        await init_gemini_chat_for_user(user_id)
        await message.answer("Готово! Контекст успешно загружен. Задавайте любые вопросы по тексту.")
    except Exception as e:
        logging.error(f"Ошибка загрузки контекста для {user_id}: {e}")
        await message.answer("Произошла ошибка при инициализации данных. Попробуйте еще раз: /start")


@dp.message()
async def message_handler(message: types.Message):
    """Обработка всех текстовых запросов к файлу"""
    user_id = message.from_user.id
    user_text = message.text

    if user_id not in user_chats:
        await message.answer("Ваша сессия не активна. Пожалуйста, отправьте /start, чтобы загрузить текст файла.")
        return

    # Эффект "печатает..." в интерфейсе Telegram
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        chat = user_chats[user_id]
        # Запрос к Gemini через фоновый поток
        response = await asyncio.to_thread(chat.send_message, user_text)
        await message.answer(response.text)
    except errors.APIError as e:
        logging.error(f"Gemini API Error для {user_id}: {e}")
        await message.answer("Ошибка со стороны ИИ. Попробуйте повторить запрос.")
    except Exception as e:
        logging.error(f"Общая ошибка для {user_id}: {e}")
        await message.answer("Не удалось получить ответ, попробуйте позже.")


async def main():
    logging.info("Поллинг бота запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

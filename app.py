import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from google import genai
from google.genai import errors
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = "8843575311:AAHAc5994cnfJwbXUfMFdagENlRvIi2hye0"
GEMINI_API_KEY = "AQ.Ab8RN6JIz59H2TAUEE8JsoFk-SHv3M4IGRYFpRFIBYlbYFIwLQ"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))
BOT_USERNAME = "arsi"  # имя бота без @

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Глобальная сессия
global_chat = None
prompt_loaded = False
large_context = ""

if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл загружен: {len(large_context)} симв.")
else:
    logging.critical(f"Файл '{FILE_NAME}' не найден!")
    sys.exit(1)


def create_chat():
    """Создаёт чат с промтом сразу в system_instruction — экономит токены"""
    return gemini_client.chats.create(
        model="gemini-2.5-flash",
        config={
            "system_instruction": (
                f"Ты полезный ассистент. Отвечай строго по этому тексту:\n\n{large_context}"
            )
        }
    )


async def ensure_session():
    """Гарантирует что сессия существует"""
    global global_chat, prompt_loaded
    if global_chat is None:
        global_chat = create_chat()
        prompt_loaded = True
        logging.info("Глобальная сессия создана, промт в system_instruction")


async def ask_gemini(user_text: str) -> str:
    """Отправляет сообщение в Gemini и возвращает ответ"""
    await ensure_session()
    response = await asyncio.to_thread(global_chat.send_message, user_text)
    return response.text


async def handle_message(message: Message, text: str):
    """Общий обработчик — отвечает в тот же чат"""
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        reply = await ask_gemini(text)
        await message.reply(reply)
    except errors.APIError as e:
        logging.error(f"Gemini API Error: {e}")
        await message.reply(f"Ошибка ИИ: {e}")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.reply("Не удалось получить ответ.")


# /start — личка
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await ensure_session()
    await message.answer(
        "Привет! База данных загружена, задавайте вопросы.\n"
        "В группе используйте: /arsi ваш вопрос"
    )


# /status — проверка загружен ли промт
@dp.message(Command("status"))
async def cmd_status(message: Message):
    if global_chat is not None and prompt_loaded:
        await message.answer("✅ Сессия активна, база данных загружена.")
    else:
        await message.answer("❌ Сессия не активна.")


# /arsi вопрос — для групп и лички
@dp.message(Command("arsi"))
async def cmd_arsi(message: Message):
    # Вытаскиваем текст после команды
    text = message.text.replace("/arsi", "", 1).strip()
    # Убираем @botusername если есть
    if text.startswith(f"@{BOT_USERNAME}"):
        text = text[len(f"@{BOT_USERNAME}"):].strip()

    if not text:
        await message.reply("Напишите вопрос после команды: /arsi ваш вопрос")
        return

    await handle_message(message, text)


# Личные сообщения (не команды) — отвечаем напрямую
@dp.message(F.chat.type == "private")
async def private_message(message: Message):
    if not message.text:
        return
    await handle_message(message, message.text.strip())


async def handle_hc(request):
    return web.Response(text="Бот онлайн!")


async def main():
    # Создаём сессию сразу при старте
    await ensure_session()

    app = web.Application()
    app.router.add_get('/', handle_hc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Веб-сервер на порту {PORT}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

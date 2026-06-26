import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from google import genai
from google.genai import errors, types as gtypes
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = "8843575311:AAHAc5994cnfJwbXUfMFdagENlRvIi2hye0"
GEMINI_API_KEY = "AQ.Ab8RN6JIz59H2TAUEE8JsoFk-SHv3M4IGRYFpRFIBYlbYFIwLQ"
FILE_NAME = "large_prompt.txt"
PORT = int(os.getenv("PORT", 8080))
BOT_USERNAME = "arsi"
MODEL = "gemini-2.5-flash"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

cache_name = None        # имя кеша на серверах Google
chat_history = []        # история сообщений глобальная
large_context = ""

if os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'r', encoding='utf-8') as f:
        large_context = f.read()
    logging.info(f"Файл загружен: {len(large_context)} симв.")
else:
    logging.critical(f"Файл '{FILE_NAME}' не найден!")
    sys.exit(1)


async def init_cache():
    """Загружает промт в кеш Google один раз при старте"""
    global cache_name
    try:
        logging.info("Создаю кеш промта на серверах Google...")

        # Загружаем файл через Files API
        uploaded = await asyncio.to_thread(
            gemini_client.files.upload,
            file=(FILE_NAME.encode(), large_context.encode('utf-8')),
            config={"mime_type": "text/plain", "display_name": "large_prompt"}
        )

        # Создаём кеш со ссылкой на файл — TTL 1 час
        cache = await asyncio.to_thread(
            gemini_client.caches.create,
            model=MODEL,
            config=gtypes.CreateCachedContentConfig(
                contents=[
                    gtypes.Content(
                        role="user",
                        parts=[gtypes.Part.from_uri(
                            file_uri=uploaded.uri,
                            mime_type="text/plain"
                        )]
                    )
                ],
                system_instruction="Ты полезный ассистент. Отвечай строго по загруженному тексту.",
                display_name="bot_prompt_cache",
                ttl="3600s"
            )
        )
        cache_name = cache.name
        logging.info(f"Кеш создан: {cache_name}")
    except Exception as e:
        logging.error(f"Ошибка создания кеша: {e}")
        logging.warning("Буду работать без кеша (через system_instruction)")
        cache_name = None


async def ask_gemini(user_text: str) -> str:
    """Отправляет вопрос, используя кеш если есть"""
    global chat_history

    chat_history.append(
        gtypes.Content(role="user", parts=[gtypes.Part(text=user_text)])
    )

    if cache_name:
        # Запрос с кешем — промт не тратит токены заново
        config = gtypes.GenerateContentConfig(
            cached_content=cache_name
        )
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=MODEL,
            contents=chat_history,
            config=config
        )
    else:
        # Fallback без кеша
        config = gtypes.GenerateContentConfig(
            system_instruction=f"Ты полезный ассистент. Отвечай по тексту:\n\n{large_context}"
        )
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=MODEL,
            contents=chat_history,
            config=config
        )

    reply = response.text
    chat_history.append(
        gtypes.Content(role="model", parts=[gtypes.Part(text=reply)])
    )

    # Не храним больше 20 сообщений чтобы не раздувать историю
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    return reply


async def handle_message(message: Message, text: str):
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


@dp.message(CommandStart())
async def cmd_start(message: Message):
    status = "✅ Кеш активен" if cache_name else "⚠️ Работаю без кеша"
    await message.answer(
        f"Привет! База данных загружена. {status}\n"
        "В группе: /arsi ваш вопрос\n"
        "Проверка: /status"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if cache_name:
        await message.answer(f"✅ Кеш активен\n`{cache_name}`\nСообщений в истории: {len(chat_history)}", parse_mode="Markdown")
    else:
        await message.answer("⚠️ Кеш не создан, работаю через system_instruction")


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
    await init_cache()

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

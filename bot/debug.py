import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command
import dotenv

dotenv.load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

router = Router()


@router.channel_post()
async def debug_channel_post(message: Message):
    print("=" * 40)
    print("CHANNEL TITLE :", message.chat.title)
    print("CHANNEL ID    :", message.chat.id)
    print("CHANNEL TYPE  :", message.chat.type)
    print("=" * 40)


@router.message(Command("ping"))
async def ping(message: Message):
    await message.answer("pong")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(router)

    print("🤖 Bot started. Send any post to the channel.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

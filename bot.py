import asyncio
import os
from bot.debug import router as bot_debug
from bot.payments import router as bot_payments
from aiogram import Bot, Dispatcher
from core.mongo import init_database
from utils.scheduler_bot import Scheduler
from core.logger import bot_logger
import dotenv

dotenv.load_dotenv()
logger = bot_logger


async def main():
    logger.info("🚀 Старт приложения")

    await init_database()

    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()

    dp.include_router(bot_debug)
    dp.include_router(bot_payments)
    scheduler = Scheduler(bot)
    scheduler.setup()
    await scheduler.start()

    logger.info("****🤖 BOT STARTED****")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.scheduler.shutdown()
        await bot.session.close()
        logger.warning("****BOT SHUTDOWN****")

if __name__ == "__main__":
    asyncio.run(main())
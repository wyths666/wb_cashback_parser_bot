import asyncio
import os
from aiogram import Bot
from core.mongo import init_database
from utils.scheduler import Scheduler
from core.logger import bot_logger
import dotenv

dotenv.load_dotenv()
logger = bot_logger


async def main():
    logger.info("🚀 Старт приложения")

    bot = Bot(token=os.getenv("BOT_TOKEN"))
    scheduler = Scheduler(bot)
    scheduler.setup()

    try:
        await init_database()
        await scheduler.start()
        logger.info("****STARTED****")

        # 🔒 держим процесс живым
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logger.error(f"Ошибка приложения - {e}")

    finally:
        scheduler.scheduler.shutdown()
        await bot.session.close()
        logger.warning("****SHUTDOWN****")


if __name__ == "__main__":
    asyncio.run(main())

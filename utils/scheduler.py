import asyncio
from datetime import datetime, timedelta, UTC
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import os
import dotenv
from mongo_db.models import User
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from core.logger import scheduler_logger

dotenv.load_dotenv()
logger = scheduler_logger
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ACCESS_DAYS = 30


class Scheduler:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        self.parser_lock = asyncio.Lock()
        self.publish_lock = asyncio.Lock()

    def setup(self):
        # 06:00 — фильтрация
        self.scheduler.add_job(
            self.filter_products,
            CronTrigger(hour=6, minute=0),
            id="filter",
            replace_existing=True,
        )

        # 06:20 — парсер фото
        self.scheduler.add_job(
            self.parse_photos,
            CronTrigger(hour=6, minute=20),
            id="photos",
            replace_existing=True,
        )

        # 23:50 — парсер товаров
        self.scheduler.add_job(
            self.parse_raw_products,
            CronTrigger(hour=23, minute=50),
            id="raw",
            replace_existing=True,
        )


    async def start(self):
        self.scheduler.start()
        logger.info("⏰ Планировщик запущен")

    # ===== задачи =====

    async def filter_products(self):
        logger.info("⏳ filter_products ждёт lock")
        async with self.parser_lock:
            logger.info("🔎 Запуск фильтрации товаров")
            from mongo_db.filter_products import filter_products

            await filter_products()

    async def parse_photos(self):
        logger.info("⏳ parse_photos ждёт lock")
        async with self.parser_lock:
            logger.info("📸 Запуск парсера фото")
            from parser.photo_url import run_photo_parser

            await run_photo_parser()

    async def parse_raw_products(self):
        logger.info("⏳ parse_raw_products ждёт lock")
        async with self.parser_lock:
            logger.info("📦 Запуск парсера товаров")
            from parser.raw_all import run_raw_parser

            await run_raw_parser()





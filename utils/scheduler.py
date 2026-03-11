import asyncio
import os
import dotenv
from bot.public_service import run_single_post_service, run_chat_post_service
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
        # парсер товаров
        self.scheduler.add_job(
            self.start_free_parser,
            CronTrigger(hour=22, minute=0),
            id="pars_free_products",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self.parse_raw_products,
            CronTrigger(hour=0, minute=5),
            id="raw",
            replace_existing=True,
        )


        # фильтрация
        self.scheduler.add_job(
            self.filter_products,
            CronTrigger(hour=3, minute=0),
            id="filter",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self.filter_products_cb,
            CronTrigger(hour=3, minute=30),
            id="filter_cb",
            replace_existing=True,
        )

        # парсер фото
        self.scheduler.add_job(
            self.parse_cb_photos,
            CronTrigger(hour=4, minute=0),
            id="photos_CB",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self.parse_photos,
            CronTrigger(hour=5, minute=0),
            id="photos",
            replace_existing=True,
        )


        # публикации
        self.scheduler.add_job(
            self.safe_channel_post,
            "cron",
            minute="*/15",
            second=0,
            hour="8-21",
            id="post_channel",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self.safe_channel_post,
            "cron",
            minute=0,
            second=0,
            hour=22,
            id="post_channel_last",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self.safe_chat_post,
            "cron",
            minute="*/30",
            second=0,
            hour="8-21",
            id="post_chat",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self.safe_chat_post,
            "cron",
            minute=0,
            second=0,
            hour=22,
            id="post_chat_last",
            replace_existing=True,
        )



    async def start(self):
        self.scheduler.start()
        logger.info("⏰ Планировщик запущен")

    # ===== задачи =====
    async def safe_channel_post(self):
        async with self.publish_lock:
            await run_single_post_service(self.bot, "@sell_magazine")

    async def safe_chat_post(self):
        async with self.publish_lock:
            await run_chat_post_service(self.bot, "@za_otzyv_ot_0")


    async def filter_products(self):
        logger.info("⏳ filter_products ждёт lock")
        async with self.parser_lock:
            logger.info("🔎 Запуск фильтрации товаров")
            from mongo_db.filter_products import filter_discount_products

            await filter_discount_products()

    async def filter_products_cb(self):
        logger.info("⏳ filter_products ждёт lock")
        async with self.parser_lock:
            logger.info("🔎 Запуск фильтрации товаров CB")
            from mongo_db.filter_products import filter_products

            await filter_products()

    async def parse_photos(self):
        logger.info("⏳ parse_photos ждёт lock")
        async with self.parser_lock:
            logger.info("📸 Запуск парсера фото")
            from parser.photo_url_for_discount import run_free_photo_parser

            await run_free_photo_parser()


    async def parse_cb_photos(self):
        logger.info("⏳ parse_photos ждёт lock")
        async with self.parser_lock:
            logger.info("📸 Запуск парсера фото CB")
            from parser.photo_url import run_photo_parser

            await run_photo_parser()


    async def parse_raw_products(self):
        logger.info("⏳ parse_raw_products ждёт lock")
        async with self.parser_lock:
            logger.info("📦 Запуск парсера товаров CB")
            from parser.raw_all import run_raw_parser

            await run_raw_parser()

    async def start_free_parser(self):
        logger.info("⏳ parse_raw_products ждёт lock")
        async with self.parser_lock:
            logger.info("📦 Запуск парсера товаров")
            from parser.raw_all import run_free_parser

            await run_free_parser()






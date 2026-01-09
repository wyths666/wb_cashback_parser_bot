import asyncio
from collections import Counter
from datetime import datetime, timezone
from typing import Dict
from aiogram.exceptions import TelegramRetryAfter
from core.mongo import init_database
from core.logger import bot_logger
from core.bot import bot
from mongo_db.models import WBProductFiltered

from bot.newsletter import (
    build_publish_pool,
    publish_product_album,
    DAILY_QUOTA, CATEGORY_WEIGHTS,
)

logger = bot_logger
UTC = timezone.utc

POSTS_TO_PREPARE = 467
FAST_DELAY_SECONDS = 30   # минимальная задержка между постами
PREVIEW_LIMIT = 20       # сколько показать в логах

async def safe_send_media_group(bot, **kwargs):
    while True:
        try:
            return await bot.send_media_group(**kwargs)

        except TelegramRetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"⏳ Flood control. Sleep {wait}s")
            await asyncio.sleep(wait)

async def bulk_publish_preview():
    await init_database()

    logger.info(f"📦 Формируем пул из {POSTS_TO_PREPARE} товаров...")

    publish_pool = await build_publish_pool(
        posts_per_day=POSTS_TO_PREPARE,
        base_weights=CATEGORY_WEIGHTS,
    )

    if not publish_pool:
        logger.warning("📭 Пул пуст")
        return

    # ---------- статистика по категориям ----------
    category_stats: Dict[str, int] = Counter(
        p.category_id for p in publish_pool
    )

    logger.info("📊 Статистика по категориям:")
    for category, count in category_stats.items():
        logger.info(f"  • {category}: {count}")

    logger.info(f"🧮 Всего товаров: {len(publish_pool)}")

    # ---------- превью ----------
    logger.info(f"🔍 Превью первых {PREVIEW_LIMIT} товаров:")
    for i, product in enumerate(publish_pool[:PREVIEW_LIMIT], start=1):
        logger.info(
            f"{i:02d}. "
            f"{product.category_id} | "
            f"nm_id={product.nm_id} | "
            f"cashback={product.cashback_percent:.2%}"
        )

    # ---------- подтверждение ----------
    answer = input("\n🚀 Опубликовать ВСЕ эти товары в канал? (y/n): ").strip().lower()

    if answer != "y":
        logger.warning("⛔ Публикация отменена пользователем")
        return

    logger.warning("🔥 НАЧИНАЕМ МАССОВУЮ ПУБЛИКАЦИЮ")

    published = 0

    for product in publish_pool:
        await publish_product_album(bot, product)
        published += 1
        await asyncio.sleep(FAST_DELAY_SECONDS)
        logger.info(f"{published}")
    logger.info(f"✅ Массовая публикация завершена: {published} товаров")


if __name__ == "__main__":
    asyncio.run(bulk_publish_preview())

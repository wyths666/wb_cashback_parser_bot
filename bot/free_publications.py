import asyncio
import html
import os
import dotenv
import random
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from aiogram.types import InputMediaPhoto
from bot.newsletter import PUBLISH_WINDOW_SECONDS
from core.logger import bot_logger
from mongo_db.models import WBProductFiltered

dotenv.load_dotenv()
logger = bot_logger
FREE_POSTS_PER_DAY = 5
FREE_CHANNEL_USERNAME = os.getenv("FREE_CHANNEL_USERNAME")
UTC = timezone.utc
dotenv.load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")



async def build_free_publish_pool(
    posts_per_day: int = 5,
) -> List[WBProductFiltered]:

    publish_pool: List[WBProductFiltered] = []
    used_nm_ids: set[int] = set()

    # =====================================================
    # 1️⃣ получаем все доступные категории
    # =====================================================
    categories = await WBProductFiltered.distinct(
        "category_id",
        {
            "published": False,
            "published_free": {"$ne": True},
            "photos_parsed": True,
        }
    )

    if not categories:
        logger.warning("📭 Нет товаров для free-публикации")
        return []

    random.shuffle(categories)
    # =====================================================
    # 2️⃣ по одному товару из каждой категории
    # =====================================================
    for category in categories:
        if len(publish_pool) >= posts_per_day:
            break

        product = await WBProductFiltered.find(
            {
                "category_id": category,
                "published": False,
                "published_free": {"$ne": True},
                "photos_parsed": True,
            }
        ).sort("cashback_percent").first_or_none()

        if not product:
            continue

        publish_pool.append(product)
        used_nm_ids.add(product.nm_id)

    # =====================================================
    # 3️⃣ если категорий меньше, чем постов → добор
    # =====================================================
    remaining = posts_per_day - len(publish_pool)

    if remaining > 0:
        logger.warning(f"⚠️ Free-добор: {remaining}")

        extra = await WBProductFiltered.find(
            {
                "published": False,
                "published_free": {"$ne": True},
                "photos_parsed": True,
                "nm_id": {"$nin": list(used_nm_ids)},
            }
        ).sort("-cashback_percent").limit(remaining).to_list()

        publish_pool.extend(extra)

    logger.info(
        f"🆓 Free publish pool: {len(publish_pool)}/{posts_per_day}"
    )

    return publish_pool

def build_free_caption(product: WBProductFiltered) -> str:
    name = html.escape(product.data.get("name", ""))
    price = round(product.price)
    cashback = round(product.cashback_percent * 100)
    rating = product.data.get("reviewRating")
    fbc_cnt = product.data.get("feedbacks")
    nm_id = product.nm_id

    url = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"

    return (
        f"🟠 <b>{name}</b>\n"
        f"⭐ {rating} · {fbc_cnt} оценок\n"
        f"💰 <b>Цена:</b> {price}₽\n"
        f"🔥 <b>Рубли за отзыв:</b> {cashback}%\n\n"
        f"📦 <a href=\"{url}\">Посмотреть товар</a>\n\n"
        f"Максимальные кэшбеки 50–100+% мы публикуем не здесь\n"
        f"Всё — в закрытом канале\n"
        f"Переходи по ссылке <a href=\"https://t.me/lovecwbbot?start\">@lovecwbbot</a>"
    )


async def publish_free_product_album(bot, product):
    try:
        caption = build_free_caption(product)
        photos = product.photos[:6]

        media = []
        for i, url in enumerate(photos):
            if i == 0:
                media.append(
                    InputMediaPhoto(
                        media=url,
                        caption=caption,
                        parse_mode="HTML",
                    )
                )
            else:
                media.append(InputMediaPhoto(media=url))

        messages = await bot.send_media_group(
            chat_id=FREE_CHANNEL_USERNAME,
            media=media,
        )

        message_ids = [msg.message_id for msg in messages]

        await product.set(
            {
                "published_free": True,
                "published_free_at": datetime.now(UTC),
                "published_free_message_ids": message_ids,
            }
        )

        logger.info(
            f"📢 Опубликован free nm_id={product.nm_id} | "
            f"фото={len(photos)} | "
            f"messages={message_ids}"
        )

    except Exception:
        logger.exception(
            f"❌ Ошибка публикации nm_id={product.nm_id}"
        )


class FreePublishService:
    def __init__(self, bot):
        self.bot = bot

    async def run(self):
        total = 0
        publish_pool = await build_free_publish_pool(
            posts_per_day=FREE_POSTS_PER_DAY
        )

        if not publish_pool:
            logger.info("📭 Нет товаров для публикации")
            return

        posts_today = len(publish_pool)

        if posts_today < FREE_POSTS_PER_DAY:
            logger.warning(
                f"⚠️ Недостаточно товаров в БД: {posts_today}/{FREE_POSTS_PER_DAY}"
            )

        delay = PUBLISH_WINDOW_SECONDS // posts_today
        delay = max(delay, 60)


        logger.info(
            f"🌀 Публикуем {posts_today} товаров | delay={delay/60} мин"
        )

        random.shuffle(publish_pool)

        for product in publish_pool:
            await publish_free_product_album(self.bot, product)
            total += 1
            next_time = datetime.now() + timedelta(seconds=delay)
            logger.info(f"⏭ Следующий пост в {next_time:%H:%M:%S}")
            await asyncio.sleep(delay)

        logger.info(f"📊 Опубликовано за запуск: {total}")


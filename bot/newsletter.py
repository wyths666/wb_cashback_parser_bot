import asyncio
import math
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InputMediaPhoto
from core.logger import bot_logger
from core.mongo import init_database
from mongo_db.models import WBProductFiltered
import dotenv
import random
from collections import Counter, defaultdict



dotenv.load_dotenv()
logger = bot_logger
UTC = timezone.utc
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
PUBLISH_WINDOW_SECONDS = 16 * 60 * 60  # 57600
POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY"))
DELAY_SECONDS = PUBLISH_WINDOW_SECONDS // POSTS_PER_DAY
CATEGORY_WEIGHTS = {
    "woman_clothes": 0.30,   # 30%
    "technics": 0.20,        # 20%
    "home_goods": 0.20,      # 20%
    "woman_shoes": 0.15,     # 15%
    "bijouterie": 0.05,      # 5%
    "cosmetics": 0.05,       # 5%
    "parfum": 0.05,          # 5%
}

def calculate_daily_quota(
    posts_per_day: int,
    weights: Dict[str, float],
) -> Dict[str, int]:
    """
    Возвращает квоты по категориям так,
    чтобы сумма всегда == posts_per_day
    """

    # 1️⃣ сырые значения
    raw = {
        cat: posts_per_day * weight
        for cat, weight in weights.items()
    }

    # 2️⃣ округляем вниз
    quota = {
        cat: math.floor(value)
        for cat, value in raw.items()
    }

    # 3️⃣ считаем остаток
    remainder = posts_per_day - sum(quota.values())

    if remainder <= 0:
        return quota

    # 4️⃣ сортируем по дробной части (убывание)
    fractions = sorted(
        raw.items(),
        key=lambda x: x[1] - math.floor(x[1]),
        reverse=True,
    )

    # 5️⃣ раздаём остаток
    for i in range(remainder):
        cat = fractions[i][0]
        quota[cat] += 1

    return quota

DAILY_QUOTA = calculate_daily_quota(
    posts_per_day=POSTS_PER_DAY,
    weights=CATEGORY_WEIGHTS,
)

def build_category_sequence(
    daily_quota: Dict[str, int],
) -> List[str]:
    """
    Превращает квоты в равномерную последовательность категорий
    """
    sequence = []

    max_len = max(daily_quota.values())

    for i in range(max_len):
        for category, count in daily_quota.items():
            if i < count:
                sequence.append(category)

    return sequence



async def build_publish_pool(
    posts_per_day: int,
    base_weights: Dict[str, float],
) -> List[WBProductFiltered]:

    publish_pool: List[WBProductFiltered] = []
    used_nm_ids: set[int] = set()
    category_fact: Counter = Counter()

    # =====================================================
    # 1️⃣ считаем доступность товаров по категориям
    # =====================================================
    available_by_category: Dict[str, int] = {}

    for category in base_weights:
        available_by_category[category] = await WBProductFiltered.find(
            {
                "category_id": category,
                "published": False,
                "photos_parsed": True,
            }
        ).count()

    total_available = sum(available_by_category.values())

    if total_available == 0:
        logger.warning("📭 Нет доступных товаров для публикации")
        return []

    # =====================================================
    # 2️⃣ целевые квоты по стратегии (base_weights)
    # =====================================================
    target_quota: Dict[str, int] = {
        cat: round(posts_per_day * weight)
        for cat, weight in base_weights.items()
    }

    # =====================================================
    # 3️⃣ ограничиваем квоты доступностью
    # =====================================================
    actual_quota: Dict[str, int] = {
        cat: min(target_quota[cat], available_by_category[cat])
        for cat in base_weights
    }

    # =====================================================
    # 4️⃣ перераспределяем остаток (если есть)
    # =====================================================
    remaining = posts_per_day - sum(actual_quota.values())

    while remaining > 0:
        candidates = [
            cat for cat in base_weights
            if available_by_category[cat] > actual_quota[cat]
        ]

        if not candidates:
            break

        # приоритет по стратегии
        cat = max(candidates, key=lambda c: base_weights[c])
        actual_quota[cat] += 1
        remaining -= 1

    # =====================================================
    # 5️⃣ строим category-sequence с anti-repeat
    # =====================================================
    sequence: List[str] = []
    quota_left = actual_quota.copy()
    last_category = None

    while len(sequence) < posts_per_day and quota_left:
        candidates = [
            cat for cat, left in quota_left.items()
            if left > 0 and cat != last_category
        ]

        if not candidates:
            candidates = [
                cat for cat, left in quota_left.items()
                if left > 0
            ]

        cat = max(candidates, key=lambda c: quota_left[c])
        sequence.append(cat)

        quota_left[cat] -= 1
        last_category = cat

        if quota_left[cat] <= 0:
            del quota_left[cat]

    # =====================================================
    # 6️⃣ наполняем пул товарами (по cashback)
    # =====================================================
    for category in sequence:
        product = await WBProductFiltered.find(
            {
                "category_id": category,
                "published": False,
                "photos_parsed": True,
                "nm_id": {"$nin": list(used_nm_ids)},
            }
        ).sort(
            [
                ("filtered_at", -1),  # СНАЧАЛА свежесть
                ("cashback_percent", -1),  # ПОТОМ процент
            ]
        ).first_or_none()

        if not product:
            continue

        publish_pool.append(product)
        used_nm_ids.add(product.nm_id)
        category_fact[category] += 1

        if len(publish_pool) >= posts_per_day:
            break

    # =====================================================
    # 7️⃣ глобальный мягкий добор (крайний случай)
    # =====================================================
    remaining = posts_per_day - len(publish_pool)

    if remaining > 0:
        logger.warning(f"⚠️ Глобальный добор: {remaining}")

        extra = await WBProductFiltered.find(
            {
                "published": False,
                "photos_parsed": True,
                "nm_id": {"$nin": list(used_nm_ids)},
            }
        ).sort("-cashback_percent").limit(remaining).to_list()

        publish_pool.extend(extra)

    # =====================================================
    # 8️⃣ DEBUG-лог
    # =====================================================
    logger.info("📊 target → actual → fact")

    for cat in base_weights:
        logger.info(
            f"{cat:<14} "
            f"{target_quota.get(cat,0):>3} → "
            f"{actual_quota.get(cat,0):>3} → "
            f"{category_fact.get(cat,0):>3}"
        )

    logger.info(f"🧮 Итого: {len(publish_pool)}/{posts_per_day}")

    return publish_pool


def build_caption(product: WBProductFiltered) -> str:
    name = product.data.get("name")
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
        f"📦 <a href=\"{url}\">Посмотреть товар</a>"
    )


async def publish_product_album(bot, product):
    try:
        caption = build_caption(product)
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

        # ⬅️ ВАЖНО: получаем список Message

        messages = await bot.send_media_group(
            chat_id=CHANNEL_ID,
            media=media,
        )

        message_ids = [msg.message_id for msg in messages]

        await product.set(
            {
                "published": True,
                "published_at": datetime.now(UTC),
                "telegram_message_ids": message_ids,
            }
        )

        logger.info(
            f"📢 Опубликован nm_id={product.nm_id} | "
            f"фото={len(photos)} | "
            f"messages={message_ids}"
        )

    except Exception:
        logger.exception(
            f"❌ Ошибка публикации nm_id={product.nm_id}"
        )

class PublishService:
    def __init__(self, bot):
        self.bot = bot

    async def run(self):
        total = 0
        publish_pool = await build_publish_pool(
            posts_per_day=POSTS_PER_DAY,
            base_weights=CATEGORY_WEIGHTS,
        )

        if not publish_pool:
            logger.info("📭 Нет товаров для публикации")
            return

        posts_today = len(publish_pool)

        if posts_today < POSTS_PER_DAY:
            logger.warning(
                f"⚠️ Недостаточно товаров в БД: {posts_today}/{POSTS_PER_DAY}"
            )

        delay = PUBLISH_WINDOW_SECONDS // posts_today
        delay = max(delay, 60)

        random.shuffle(publish_pool)

        logger.info(
            f"🌀 Публикуем {posts_today} товаров | delay={delay/60} мин"
        )

        for product in publish_pool:
            await publish_product_album(self.bot, product)
            total += 1
            next_time = datetime.now() + timedelta(seconds=delay)
            logger.info(f"⏭ Следующий пост в {next_time:%H:%M:%S}")
            await asyncio.sleep(delay)

        logger.info(f"📊 Опубликовано за запуск: {total}")






import asyncio
import html
import random
from datetime import datetime, UTC
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

from core.bot import bot
from core.logger import bot_logger
from core.mongo import init_database
from mongo_db.models import WBProductDiscount, ParserSettings, WBProductFiltered

logger = bot_logger


CATEGORIES = [
    "technics",
    "woman_clothes",
    "woman_shoes",
    "cosmetics",
    "parfum",
    "bijouterie",
    "home_goods",
    "kids"
]


async def get_category_index() -> int:
    settings = await ParserSettings.find_one(
        ParserSettings.key == "post_rotation"
    )

    if not settings:
        settings = ParserSettings(
            key="post_rotation",
            category_index=0
        )
        await settings.insert()

    return settings.category_index

async def get_chat_category_index() -> int:
    settings = await ParserSettings.find_one(
        ParserSettings.key == "chat_rotation"
    )

    if not settings:
        settings = ParserSettings(
            key="chat_rotation",
            chat_category_index=0
        )
        await settings.insert()

    return settings.chat_category_index


async def set_category_index(index: int):

    settings = await ParserSettings.find_one(
        ParserSettings.key == "post_rotation"
    )

    if not settings:
        settings = ParserSettings(
            key="post_rotation",
            category_index=index
        )
        await settings.insert()
        return

    settings.category_index = index
    settings.updated_at = datetime.now(UTC)

    await settings.save()


async def set_chat_category_index(index: int):

    settings = await ParserSettings.find_one(
        ParserSettings.key == "chat_rotation"
    )

    if not settings:
        settings = ParserSettings(
            key="chat_rotation",
            chat_category_index=index
        )
        await settings.insert()
        return

    settings.chat_category_index = index
    settings.chat_updated_at = datetime.now(UTC)

    await settings.save()


async def get_single_product():

    category_index = await get_category_index()

    logger.info(f"📊 Текущий индекс категории: {category_index}")

    for _ in range(len(CATEGORIES)):

        category = CATEGORIES[category_index]

        logger.info(f"🔍 Проверяем категорию: {category}")

        products = await (
            WBProductDiscount.find(
                WBProductDiscount.category_id == category,
                WBProductDiscount.published == False,
                WBProductDiscount.photos_parsed == True
            )
            .sort("-created_at")
            .limit(50)
            .to_list()
        )

        next_index = (category_index + 1) % len(CATEGORIES)

        await set_category_index(next_index)

        if not products:
            logger.warning(f"⚠️ Нет товаров в категории {category}")
            category_index = next_index
            continue

        product = random.choice(products)

        logger.info(
            f"✅ Выбран товар | "
            f"категория={category} | "
            f"nm_id={product.nm_id}"
        )

        return product

    logger.warning("❌ Не удалось найти товар ни в одной категории")

    return None


async def get_single_chat_product():

    category_index = await get_chat_category_index()

    logger.info(f"📊 Текущий индекс категории: {category_index}")

    for _ in range(len(CATEGORIES)):

        category = CATEGORIES[category_index]

        logger.info(f"🔍 Проверяем категорию: {category}")

        products = await (
            WBProductFiltered.find(
                WBProductFiltered.category_id == category,
                WBProductFiltered.published == False,
                WBProductFiltered.photos_parsed == True
            )
            .sort("-created_at")
            .limit(50)
            .to_list()
        )

        next_index = (category_index + 1) % len(CATEGORIES)

        await set_chat_category_index(next_index)

        if not products:
            logger.warning(f"⚠️ Нет товаров в категории {category}")
            category_index = next_index
            continue

        product = random.choice(products)

        logger.info(
            f"✅ Выбран товар | "
            f"категория={category} | "
            f"nm_id={product.nm_id}"
        )

        return product

    logger.warning("❌ Не удалось найти товар ни в одной категории")

    return None



def build_single_post(product):

    name = product.data.get("name", "Товар")

    link = f"https://www.wildberries.ru/catalog/{product.nm_id}/detail.aspx"
    review = f"https://www.wildberries.ru/catalog/{product.nm_id}/feedbacks"
    economy = int(product.basic_price - product.price)

    text = f"""
🔥 <b>Горячая находка</b>

<b>{name}</b>

❌ Обычная цена: {int(product.basic_price)}₽ 
✅ Цена со скидкой: <b>{int(product.price)}₽</b>
💸 Экономия: {economy}₽

⭐ Рейтинг: {product.rating} | 📝 {product.feedbacks} отзывов
Артикул: {product.nm_id}

<a href="{link}">🛍 Купить на Wildberries ▸</a>
      
<a href="{review}">💬 Читать отзывы ▸</a>
"""

    return text.strip()


def build_chat_caption(product: WBProductFiltered) -> str:
    name = html.escape(product.data.get("name", ""))
    basic_price = round(product.data["sizes"][0]["price"]["basic"] / 100)
    price = round(product.price)
    cashback = round(product.cashback)
    rating = product.data.get("reviewRating")
    fbc_cnt = product.data.get("feedbacks")
    nm_id = product.nm_id

    url = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"

    return (
        f"🔥 <b>Горячий кэшбэк</b>\n\n"
        f"🟠 <b>{name}</b>\n\n"
        f"⭐ {rating} | 📝 {fbc_cnt} отзывов\n"
        f"❌ Обычная цена: {basic_price}₽\n" 
        f"✅ Цена со скидкой: {price}₽\n"
        f"💸 <b>Рубли за отзыв:</b> {cashback}₽\n\n"
        f"💴 <><"
        f"🛍 <a href=\"{url}\"> Купить на Wildberries</a>\n\n"

    )


async def publish_single_product(bot, chat_id, product):
    text = build_single_post(product)
    photo = product.photos[0]
    msg = await bot.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=text,
        parse_mode="HTML",
    )

    await product.set({
        "published": True,
        "published_at": datetime.now(UTC),
        "telegram_message_ids": [msg.message_id]
    })


async def publish_chat_product(bot, chat_id, product):
    caption = build_chat_caption(product)
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
        chat_id=chat_id,
        media=media,
    )

    message_ids = [msg.message_id for msg in messages]

    await product.set({
        "published": True,
        "published_at": datetime.now(UTC),
        "telegram_message_ids": message_ids
    })

async def run_single_post_service(bot, chat_id):
    product = await get_single_product()

    if not product:
        logger.info("Нет товаров для публикации")
        return

    await publish_single_product(bot, chat_id, product)


async def run_chat_post_service(bot, chat_id):
    product = await get_single_chat_product()

    if not product:
        logger.info("Нет товаров для публикации")
        return

    await publish_chat_product(bot, chat_id, product)


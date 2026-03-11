import asyncio
from datetime import datetime, timezone, UTC
from core.logger import parser_logger
from core.mongo import init_database
from mongo_db.models import WBProductRaw, WBProductFiltered, WBProductDiscount
from parser.raw_all import calc_data_hash

logger = parser_logger

def extract_prices(product: dict) -> tuple[float, float]:
    prices = []
    basics = []

    for size in product.get("sizes", []):
        p = size.get("price", {}).get("product")
        b = size.get("price", {}).get("basic")

        if p and p > 0:
            prices.append(p)

        if b and b > 0:
            basics.append(b)

    if not prices or not basics:
        return 0, 0

    product_price = min(prices) / 100
    basic_price = min(basics) / 100

    return product_price, basic_price

def calc_discount(product_price: float, basic_price: float) -> float:
    if basic_price <= 0:
        return 0

    return (basic_price - product_price) / basic_price



def calc_cashback_percent(product: dict) -> float:
    cashback = product.get("feedbackPoints")
    if not cashback or cashback <= 0:
        return 0.0

    prices = []

    for size in product.get("sizes", []):
        price = size.get("price", {}).get("product")
        if price and price > 0:
            prices.append(price)

    if not prices:
        return 0.0

    min_price_rub = min(prices) / 100  # ⬅️ копейки → рубли

    return cashback / min_price_rub

def detect_fulfillment(product: dict) -> tuple[str, int]:
    score = 0

    wh = product.get("wh")
    time1 = product.get("time1")
    supplier_flags = product.get("supplierFlags", 0)

    if wh == 300571:
        score += 2

    if isinstance(time1, int) and time1 <= 3:
        score += 1

    if supplier_flags:
        score += 1

    if score >= 3:
        return "FBO", score
    elif score == 2:
        return "LIKELY_FBO", score
    else:
        return "FBS", score



async def filter_products(
    min_percent: float = 0.30,
    allow_likely_fbo: bool = True
):
    raw_products = await WBProductRaw.find_all().to_list()

    passed = 0
    skipped_fbs = 0
    skipped_unchanged = 0

    for doc in raw_products:
        product = doc.data
        data_hash = calc_data_hash(product)

        filtered_existing = await WBProductFiltered.find_one(
            WBProductFiltered.nm_id == doc.nm_id
        )

        # 🔒 1. ОПУБЛИКОВАННЫЕ НЕ ТРОГАЕМ ВООБЩЕ
        if filtered_existing and filtered_existing.published:
            skipped_unchanged += 1
            continue

        # 🔁 2. Если есть и hash не изменился — пропускаем
        if filtered_existing and filtered_existing.source_hash == data_hash:
            skipped_unchanged += 1
            continue

        # 3️⃣ cashback %
        percent = calc_cashback_percent(product)
        if percent < min_percent:
            if filtered_existing:
                await filtered_existing.set({
                    "source_hash": data_hash,
                    "filtered_at": datetime.now(UTC),
                })
            continue

        # 4️⃣ fulfillment
        fulfillment, score = detect_fulfillment(product)

        if fulfillment == "FBS" or (
            fulfillment == "LIKELY_FBO" and not allow_likely_fbo
        ):
            skipped_fbs += 1
            if filtered_existing:
                await filtered_existing.set({
                    "source_hash": data_hash,
                    "filtered_at": datetime.now(UTC),
                })
            continue

        # 5️⃣ цена
        prices = [
            size["price"]["product"]
            for size in product.get("sizes", [])
            if size.get("price", {}).get("product", 0) > 0
        ]
        if not prices:
            continue

        min_price_rub = min(prices) / 100
        cashback = product.get("feedbackPoints", 0)

        update_data = {
            "cashback_percent": round(percent, 4),
            "price": min_price_rub,
            "cashback": cashback,
            "category_id": doc.category_id,
            "fulfillment": fulfillment,
            "fulfillment_score": score,
            "data": product,
            "source_hash": data_hash,
            "filtered_at": datetime.now(UTC),
        }

        # ✅ 6. UPDATE или INSERT (БЕЗ UPSERT)
        if filtered_existing:
            await filtered_existing.set(update_data)
        else:
            await WBProductFiltered(
                nm_id=doc.nm_id,
                **update_data,
                published=False,
                published_at=None,
                telegram_message_ids=None,
            ).insert()

        passed += 1

    logger.info(
        f"Фильтр ≥ {min_percent*100:.0f}% | "
        f"прошли: {passed}, "
        f"отсеяно FBS: {skipped_fbs}, "
        f"без изменений: {skipped_unchanged}, "
        f"batch: {len(raw_products)}"
    )


async def filter_discount_products():

    raw_products = await WBProductRaw.find_all().to_list()

    passed = 0
    skipped_unchanged = 0

    for doc in raw_products:

        product = doc.data
        data_hash = calc_data_hash(product)

        existing = await WBProductDiscount.find_one(
            WBProductDiscount.nm_id == doc.nm_id
        )

        if existing and existing.published:
            continue

        if existing and existing.source_hash == data_hash:
            skipped_unchanged += 1
            continue

        price, basic_price = extract_prices(product)

        if price == 0 or basic_price == 0:
            continue

        # 150 – 1500 ₽
        if not (150 <= price <= 1500):
            continue

        discount = calc_discount(price, basic_price)

        # ≥ 40%
        if discount < 0.40:
            continue

        rating = product.get("reviewRating", 0)
        feedbacks = product.get("feedbacks", 0)

        # рейтинг
        if rating < 4.5:
            continue

        # отзывы
        if feedbacks < 50:
            continue

        update_data = {
            "price": price,
            "basic_price": basic_price,
            "discount_percent": round(discount, 4),
            "rating": rating,
            "feedbacks": feedbacks,
            "category_id": doc.category_id,
            "data": product,
            "source_hash": data_hash,
            "updated_at": datetime.now(UTC)
        }

        if existing:
            await existing.set(update_data)

        else:
            await WBProductDiscount(
                nm_id=doc.nm_id,
                **update_data,
                published=False,
                published_at=None,
                telegram_message_ids=None
            ).insert()

        passed += 1

    logger.info(
        f"Discount filter | "
        f"passed: {passed}, "
        f"unchanged: {skipped_unchanged}, "
        f"batch: {len(raw_products)}"
    )



import asyncio
from datetime import datetime, timezone, UTC
from core.logger import parser_logger
from core.mongo import init_database
from mongo_db.models import WBProductRaw, WBProductFiltered
from parser.raw_all import calc_data_hash

logger = parser_logger



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
    """
    Фильтрует raw-товары в filtered.
    Повторно обрабатывает ТОЛЬКО те товары,
    у которых изменились значимые данные.
    """

    raw_products = await WBProductRaw.find_all().to_list()

    passed = 0
    skipped_fbs = 0
    skipped_unchanged = 0

    for doc in raw_products:
        product = doc.data

        # 1️⃣ считаем hash текущих raw-данных
        data_hash = calc_data_hash(product)

        # 2️⃣ проверяем, есть ли уже filtered
        filtered_existing = await WBProductFiltered.find_one(
            WBProductFiltered.nm_id == doc.nm_id
        )

        if filtered_existing and filtered_existing.source_hash == data_hash:
            skipped_unchanged += 1
            continue

        # 3️⃣ считаем cashback %
        percent = calc_cashback_percent(product)
        if percent < min_percent:
            # если раньше был filtered — обновим hash, чтобы не дергать снова
            if filtered_existing:
                await filtered_existing.set(
                    {
                        "source_hash": data_hash,
                        "filtered_at": datetime.now(UTC),
                    }
                )
            continue

        # 4️⃣ определяем fulfillment
        fulfillment, score = detect_fulfillment(product)

        if fulfillment == "FBS":
            skipped_fbs += 1
            if filtered_existing:
                await filtered_existing.set(
                    {
                        "source_hash": data_hash,
                        "filtered_at": datetime.now(UTC),
                    }
                )
            continue

        if fulfillment == "LIKELY_FBO" and not allow_likely_fbo:
            skipped_fbs += 1
            if filtered_existing:
                await filtered_existing.set(
                    {
                        "source_hash": data_hash,
                        "filtered_at": datetime.now(UTC),
                    }
                )
            continue

        # 5️⃣ считаем минимальную цену
        prices = [
            size["price"]["product"]
            for size in product.get("sizes", [])
            if size.get("price", {}).get("product", 0) > 0
        ]

        if not prices:
            continue

        min_price_rub = min(prices) / 100
        cashback = product.get("feedbackPoints", 0)

        filtered_doc = WBProductFiltered(
            nm_id=doc.nm_id,
            cashback_percent=round(percent, 4),
            price=min_price_rub,
            cashback=cashback,
            category_id=doc.category_id,
            fulfillment=fulfillment,
            fulfillment_score=score,
            data=product,
            source_hash=data_hash,
            filtered_at=datetime.now(UTC),
        )

        # 6️⃣ upsert
        await WBProductFiltered.find_one(
            WBProductFiltered.nm_id == filtered_doc.nm_id
        ).upsert(
            {"$set": filtered_doc.dict()},
            on_insert=filtered_doc,
        )

        passed += 1

    logger.info(
        f"Фильтр ≥ {min_percent*100:.0f}% | "
        f"прошли: {passed}, "
        f"отсеяно FBS: {skipped_fbs}, "
        f"без изменений: {skipped_unchanged}, "
        f"batch: {len(raw_products)}"
    )




async def main():
    await init_database()
    await filter_products(min_percent=0.30)

if __name__ == "__main__":
    asyncio.run(main())

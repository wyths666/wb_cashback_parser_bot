import asyncio

from core.logger import parser_logger
from core.mongo import init_database
from mongo_db.models import WBProductRaw, WBProductFiltered
from parser.raw_all import calc_data_hash

logger = parser_logger


async def backfill_hashes():
    """
    1. Проставляет data_hash в WBProductRaw
    2. Проставляет source_hash в WBProductFiltered (если есть raw)
    """
    await init_database()
    raw_products = await WBProductRaw.find_all().to_list()

    raw_updated = 0
    filtered_updated = 0

    for raw in raw_products:
        product = raw.data
        data_hash = calc_data_hash(product)

        # 1️⃣ RAW — если нет data_hash
        if not getattr(raw, "data_hash", None):
            await raw.set({"data_hash": data_hash})
            raw_updated += 1

        # 2️⃣ FILTERED — если существует
        filtered = await WBProductFiltered.find_one(
            WBProductFiltered.nm_id == raw.nm_id
        )

        if filtered and not getattr(filtered, "source_hash", None):
            await filtered.set({"source_hash": data_hash})
            filtered_updated += 1

    logger.info(
        f"🧩 backfill_hashes | "
        f"raw обновлено: {raw_updated}, "
        f"filtered обновлено: {filtered_updated}, "
        f"batch: {len(raw_products)}"
    )

if __name__ == "__main__":
    asyncio.run(backfill_hashes())
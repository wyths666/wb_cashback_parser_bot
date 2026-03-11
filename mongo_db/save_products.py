from core.logger import parser_logger
from mongo_db.models import OzonProductRaw
from pymongo import ReplaceOne
from pymongo.errors import BulkWriteError

logger = parser_logger


async def save_ozon_raw_products(products: list[dict]):

    ops = []

    for p in products:

        if not p.get("price"):
            continue

        try:
            doc = OzonProductRaw(**p).model_dump()
        except Exception as e:
            logger.error(f"validation error: {e}")
            continue

        ops.append(
            ReplaceOne(
                {"sku": doc["sku"]},
                doc,
                upsert=True
            )
        )

    if not ops:
        return

    logger.info(f"save batch incoming: {len(ops)}")

    try:
        res = await OzonProductRaw.get_motor_collection().bulk_write(
            ops,
            ordered=False
        )

        logger.info(
            f"mongo result → "
            f"inserted={res.upserted_count} "
            f"modified={res.modified_count} "
            f"matched={res.matched_count}"
        )

    except BulkWriteError as e:
        logger.error(f"bulk write error: {e.details}")


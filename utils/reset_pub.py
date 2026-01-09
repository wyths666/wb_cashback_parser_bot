import asyncio
from core.mongo import init_database
from core.logger import parser_logger
from mongo_db.models import WBProductFiltered

logger = parser_logger

BATCH_SIZE = 1000


async def reset_publish_flags():
    await init_database()

    total = 0
    updated = 0

    cursor = WBProductFiltered.find_all()

    async for product in cursor:
        total += 1

        await product.set(
            {
                "published": False,
                "published_at": None,
                "telegram_message_ids": None,
            }
        )

        updated += 1

        if updated % BATCH_SIZE == 0:
            logger.info(f"♻️ Обновлено {updated} документов")

    logger.info(
        f"✅ Готово: обновлено {updated} документов (всего {total})"
    )


if __name__ == "__main__":
    asyncio.run(reset_publish_flags())

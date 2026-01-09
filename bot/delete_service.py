import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from core.logger import bot_logger
from mongo_db.models import WBProductFiltered
import dotenv


dotenv.load_dotenv()
logger = bot_logger
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))




class DeleteService:
    def __init__(self, bot):
        self.bot = bot

    async def get_product(self, nm_id: int) -> WBProductFiltered | None:
        return await WBProductFiltered.find_one(
            WBProductFiltered.nm_id == nm_id
        )

    async def delete_product(self, product: WBProductFiltered) -> None:
        if not product.telegram_message_ids:
            logger.warning(
                f"⚠️ Нет message_id для nm_id={product.nm_id}"
            )
            return

        for message_id in product.telegram_message_ids:
            try:
                await self.bot.delete_message(
                    chat_id=CHANNEL_ID,
                    message_id=message_id,
                )
            except Exception:
                logger.exception(
                    f"❌ Ошибка удаления message_id={message_id}"
                )

        await product.set(
            {
                "published": False,
                "published_at": None,
                "telegram_message_ids": None,
            }
        )

        logger.info(f"🗑 Удалён nm_id={product.nm_id}")

    async def delete_by_nm_id(self, nm_id: int) -> None:
        product = await self.get_product(nm_id)

        if not product:
            logger.warning(f"⚠️ Товар nm_id={nm_id} не найден")
            return

        await self.delete_product(product)

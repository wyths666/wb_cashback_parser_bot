import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict

from aiogram.exceptions import TelegramRetryAfter

from core.logger import bot_logger
from mongo_db.models import WBProductFiltered, WBProductRaw
import dotenv

from parser.cashback_validation import get_nm_ids_to_delete, get_nm_ids_to_delete_unpublished

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
                await asyncio.sleep(0.5)

            except TelegramRetryAfter as e:
                logger.warning(f"⏳ Flood limit, sleep {e.retry_after}s")
                await asyncio.sleep(e.retry_after)

            except Exception:
                logger.warning("❌ Ошибка удаления сообщения")

        try:
            await product.delete()
            raw = await WBProductRaw.find_one(
                WBProductRaw.nm_id == product.nm_id
            )
            if raw:
                await raw.delete()
        except Exception as e:
            logger.error(
                f"❌ Ошибка удаления из базы данных - {str(e)}"
            )


        logger.info(f"🗑 Удалён nm_id={product.nm_id}")

    async def delete_product_db_only(self, product: WBProductFiltered) -> None:
        try:
            await product.delete()
            raw = await WBProductRaw.find_one(
                WBProductRaw.nm_id == product.nm_id
            )
            if raw:
                await raw.delete()
        except Exception as e:
            logger.error(
                f"❌ Ошибка удаления из базы данных - {str(e)}"
            )
        logger.info(f"🗑 Удалён nm_id={product.nm_id}")

    async def delete_by_nm_id_unpublished(self, nm_id: int) -> None:
        product = await self.get_product(nm_id)

        if not product:
            logger.warning(f"⚠️ Товар nm_id={nm_id} не найден")
            return

        await self.delete_product_db_only(product)

    async def delete_by_nm_id(self, nm_id: int) -> None:
        product = await self.get_product(nm_id)

        if not product:
            logger.warning(f"⚠️ Товар nm_id={nm_id} не найден")
            return

        await self.delete_product(product)


    async def run(self):
        nm_ids = await get_nm_ids_to_delete()

        for nm_id in nm_ids:
            await self.delete_by_nm_id(nm_id)

    async def run_delete_unpublished(self):
        nm_ids = await get_nm_ids_to_delete_unpublished()

        for nm_id in nm_ids:
            await self.delete_by_nm_id_unpublished(nm_id)

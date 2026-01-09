import asyncio
from typing import Dict, List
from playwright.async_api import async_playwright
from core.logger import bot_logger
from mongo_db.models import WBProductFiltered
from bot.delete_service import DeleteService

logger = bot_logger

# ===== настройки =====

UCARD_VERSIONS = [5, 4, 3, 2]
BATCH_SIZE = 20
REQUEST_DELAY = 1.0

MIN_CASHBACK_PERCENT = 0.30

WB_HOME_URL = "https://www.wildberries.ru"


# ===== helpers =====

def build_ucard_url(version: int, nm_ids: List[int]) -> str:
    nm_param = ";".join(map(str, nm_ids))

    return (
        f"https://www.wildberries.ru/__internal/u-card/cards/v{version}/detail"
        f"?appType=1"
        f"&curr=rub"
        f"&dest=-1257484"
        f"&spp=30"
        f"&hide_vflags=4294967296"
        f"&hide_dtype=9"
        f"&ab_testing=false"
        f"&lang=ru"
        f"&nm={nm_param}"
    )


def extract_cashback_percent(card: dict) -> float:
    promo = card.get("promo") or {}
    cashback = promo.get("cashback")

    if not cashback:
        return 0.0

    percent = cashback.get("percent")
    if isinstance(percent, (int, float)):
        return percent / 100

    return 0.0



# ===== service =====

class ValidatePublishedOnlineService:
    def __init__(
        self,
        bot,
        min_cashback_percent: float = MIN_CASHBACK_PERCENT,
        delay_seconds: float = REQUEST_DELAY,
    ):
        self.bot = bot
        self.min_cashback_percent = min_cashback_percent
        self.delay_seconds = delay_seconds
        self.delete_service = DeleteService(bot)

    async def fetch_ucard_batch(
            page,
            nm_ids: list[int],
    ) -> dict[int, dict]:

        nm_param = ";".join(map(str, nm_ids))

        for version in UCARD_VERSIONS:
            url = build_ucard_url(version, nm_ids)

            try:
                data = await page.evaluate(
                    """
                    async (url) => {
                        const res = await fetch(url, {
                            credentials: "include",
                            headers: {
                                "accept": "application/json"
                            }
                        });
                        if (!res.ok) return null;
                        return await res.json();
                    }
                    """,
                    url,
                )

                if not data:
                    logger.warning(f"⚠️ u-card v{version} → пусто")
                    continue

                products = data.get("data", {}).get("products", [])
                if not products:
                    logger.warning(f"⚠️ u-card v{version} → нет products")
                    continue

                logger.info(f"✅ u-card v{version} использован")

                return {p["id"]: p for p in products}

            except Exception:
                logger.exception(f"❌ Ошибка u-card v{version}")

        return {}

    async def run(self):
        logger.info("🔎 Онлайн-проверка опубликованных товаров")

        products = await WBProductFiltered.find(
            {
                "published": True,
                "telegram_message_ids": {"$ne": None},
            }
        ).to_list()

        logger.info(f"📦 Найдено опубликованных: {len(products)}")

        checked = 0
        removed = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(
                locale="ru-RU",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            page = await context.new_page()

            # 🔥 ОБЯЗАТЕЛЬНЫЙ ПРОГРЕВ
            logger.info("🌍 Прогрев Wildberries")
            await page.goto(WB_HOME_URL, timeout=60_000)
            await asyncio.sleep(3)

            # ===== batch loop =====

            for i in range(0, len(products), BATCH_SIZE):
                batch = products[i : i + BATCH_SIZE]
                nm_ids = [p.nm_id for p in batch]

                try:
                    cards = await self.fetch_ucard_batch(context, nm_ids)

                    for product in batch:
                        card = cards.get(product.nm_id)

                        if not card:
                            logger.warning(
                                f"⚠️ nm_id={product.nm_id} | нет данных u-card"
                            )
                            continue

                        actual_percent = extract_cashback_percent(card)

                        if actual_percent < self.min_cashback_percent:
                            logger.warning(
                                f"🗑 nm_id={product.nm_id} | "
                                f"cashback упал: "
                                f"{product.cashback_percent:.2%} → "
                                f"{actual_percent:.2%}"
                            )
                            await self.delete_service.delete_product(product)
                            removed += 1

                        checked += 1

                    await asyncio.sleep(self.delay_seconds)

                except Exception:
                    logger.exception("❌ Ошибка batch-проверки")

            await browser.close()

        logger.info(
            f"✅ Онлайн-проверка завершена | "
            f"проверено: {checked}, "
            f"удалено: {removed}"
        )

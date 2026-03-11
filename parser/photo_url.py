import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

from playwright.async_api import BrowserContext, async_playwright
from core.logger import parser_logger
from core.mongo import init_database
from mongo_db.models import WBProductFiltered

logger = parser_logger
UTC = timezone.utc
MAX_PHOTOS = 6
MAX_BASKET = 99
SIZES = ["big", "hq"]
DOMAIN = "wbbasket.ru"

def build_image_url(
    nm_id: int,
    basket: int,
    size: str,
    image_num: str,
) -> str:
    vol = nm_id // 100_000
    part = nm_id // 1_000
    basket_str = f"{basket:02d}"

    return (
        f"https://basket-{basket_str}.wbbasket.ru/"
        f"vol{vol}/part{part}/{nm_id}/images/{size}/{image_num}.webp"
    )


async def collect_photos(context: BrowserContext, nm_id: int) -> List[str]:
    vol = nm_id // 100_000
    part = nm_id // 1_000

    for basket in range(1, MAX_BASKET + 1):
        for size in SIZES:
            url = build_image_url(nm_id, basket, size, 1)

            try:
                resp = await context.request.head(url, timeout=8_000)
                if resp.status == 200:
                    photos = [url]

                    for img_num in range(2, MAX_PHOTOS + 1):
                        next_url = build_image_url(
                            nm_id, basket, size, img_num
                        )

                        r = await context.request.head(
                            next_url, timeout=8_000
                        )
                        if r.status != 200:
                            break

                        photos.append(next_url)
                        await asyncio.sleep(0.15)

                    return photos

            except Exception:
                pass

    return []



async def reserve_products(limit: int):
    now = datetime.now(UTC)
    stale_time = now - timedelta(hours=2)

    await WBProductFiltered.find(
        {
            "reserved_for_photos": True,
            "reserved_for_photos_at": {"$lt": stale_time},
        }
    ).update(
        {
            "$set": {
                "reserved_for_photos": False,
                "reserved_for_photos_at": None,
            }
        }
    )

    # резервируем новые
    products = await WBProductFiltered.find(
        {
            "published": False,
            "photos_parsed": False,
            "reserved_for_photos": {"$ne": True},
        }
    ).limit(limit).to_list()

    if not products:
        return []

    ids = [p.id for p in products]

    await WBProductFiltered.find(
        {"_id": {"$in": ids}}
    ).update(
        {
            "$set": {
                "reserved_for_photos": True,
                "reserved_for_photos_at": now,
            }
        }
    )

    return products


class PhotoParserService:
    def __init__(
        self,
        context: BrowserContext,
        daily_limit: int = 150,
        concurrency: int = 3,
    ):
        self.context = context
        self.daily_limit = daily_limit
        self.semaphore = asyncio.Semaphore(concurrency)

    async def process_product(self, product: WBProductFiltered):
        async with self.semaphore:
            nm_id = product.nm_id

            try:
                photos = await collect_photos(self.context, nm_id)

                if photos:
                    await product.set(
                        {
                            "photos": photos,
                            "photos_parsed": True,
                            "reserved_for_photos": False,
                            "reserved_for_photos_at": None,
                        }
                    )
                    logger.info(f"📸 nm_id={nm_id} | фото={len(photos)}")
                else:
                    await product.set(
                        {
                            "reserved_for_photos": False,
                            "reserved_for_photos_at": None,
                        }
                    )
                    logger.warning(f"⚠️ nm_id={nm_id} | фото не найдены")

            except Exception as e:
                logger.exception(f"❌ nm_id={nm_id} | ошибка парсинга фото")

                await product.set(
                    {
                        "reserved_for_photos": False,
                        "reserved_for_photos_at": None,
                    }
                )

    async def run(self):
        products = await reserve_products(self.daily_limit)

        if not products:
            logger.info("📭 Нет товаров для парсинга фото")
            return

        logger.info(f"📸 Парсим фото для {len(products)} товаров")

        tasks = [
            self.process_product(p)
            for p in products
        ]

        await asyncio.gather(*tasks)


async def run_photo_parser():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ru-RU",
            user_agent="Mozilla/5.0 ..."
        )

        service = PhotoParserService(
            context=context,
            daily_limit=20000,
            concurrency=60,
        )

        await service.run()
        await browser.close()



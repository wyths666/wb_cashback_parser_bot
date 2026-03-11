import math
from datetime import datetime, timezone, UTC
from playwright.async_api import async_playwright
from core.logger import parser_logger
from core.mongo import init_database
from mongo_db.models import WBProductRaw
import asyncio
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import hashlib
import json
from parser.free_links import free_pars_links
from parser.links import pars_links
from parser.wb_session import WBSession

logger = parser_logger

CONCURRENCY = 3

def calc_data_hash(data: dict) -> str:
    relevant = {
        "sizes": data.get("sizes"),
        "feedbackPoints": data.get("feedbackPoints"),
        "time1": data.get("time1"),
        "wh": data.get("wh"),
        "supplierFlags": data.get("supplierFlags"),
    }

    raw = json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()



def set_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    query["page"] = [str(page)]

    new_query = urlencode(query, doseq=True)

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))


async def fetch_catalog_page(request, base_url, page, max_retries=5):

    url = set_page(base_url, page)

    for attempt in range(max_retries):

        try:
            response = await request.get(url, timeout=30_000)

            if response.status == 200:
                return await response.json()

        except Exception:
            logger.exception("WB request error")

        await asyncio.sleep(2)

    return None

from pymongo import UpdateOne


async def save_products(products: list, category_id: str):

    now = datetime.now(timezone.utc)

    operations = []

    for p in products:

        nm_id = p.get("id")
        if not nm_id:
            continue

        doc = {
            "nm_id": nm_id,
            "data": p,
            "data_hash": calc_data_hash(p),
            "category_id": category_id,
            "fetched_at": now,
        }

        operations.append(
            UpdateOne(
                {"nm_id": nm_id},
                {"$set": doc},
                upsert=True
            )
        )

    if not operations:
        return 0

    result = await WBProductRaw.get_motor_collection().bulk_write(
        operations,
        ordered=False
    )

    inserted = result.upserted_count
    updated = result.modified_count

    logger.info(
        f"DB: +{inserted} новых | обновлено {updated}"
    )

    return inserted


async def run_playwright_parser(api_url, category_id):
    browser = None

    MAX_NEW_PRODUCTS = 100
    new_products = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context = await browser.new_context(
                locale="ru-RU",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            page = await context.new_page()

            logger.info("1️⃣ Прогрев WB")
            await page.goto("https://www.wildberries.ru/", timeout=60_000)
            await asyncio.sleep(3)

            page_num = 1

            while True:

                logger.info(f"📄 Загружаем page={page_num}")

                data = await fetch_catalog_page(context, api_url, page_num)
                if not data:
                    break

                products = data.get("products", [])
                if not products:
                    break

                inserted = await save_products(products, category_id)

                new_products += inserted

                logger.info(
                    f"📦 Новых товаров: {inserted} | всего собрано: {new_products}"
                )

                if new_products >= MAX_NEW_PRODUCTS:
                    logger.info(
                        f"⛔ Достигнут лимит новых товаров: {MAX_NEW_PRODUCTS}"
                    )
                    break

                page_num += 1
                await asyncio.sleep(5)

    except Exception:
        logger.exception("🔥 Критическая ошибка парсера")

    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                logger.exception("❌ Ошибка при закрытии браузера")

async def parse_single_url(session, url, category_id):

    MAX_NEW_PRODUCTS = 100
    new_products = 0
    page_num = 1

    while True:

        logger.info(f"📄 {category_id} page={page_num}")

        data = await fetch_catalog_page(
            session.request,
            url,
            page_num
        )

        if not data:
            break

        products = data.get("products", [])
        if not products:
            break

        inserted = await save_products(products, category_id)

        new_products += inserted

        if new_products >= MAX_NEW_PRODUCTS:
            logger.info(
                f"⛔ {category_id} достигнут лимит {MAX_NEW_PRODUCTS}"
            )
            break

        page_num += 1
        await asyncio.sleep(1.5)

async def run_raw_parser():

    session = WBSession()
    await session.start()

    semaphore = asyncio.Semaphore(3)

    async def worker(url, category_id):

        async with semaphore:
            try:
                logger.info(
                    f"🔗 Парсинг {category_id}: {url}"
                )

                await parse_single_url(
                    session,
                    url,
                    category_id
                )

            except Exception:
                logger.exception("❌ Ошибка парсинга")

    tasks = []

    for category_id, urls in pars_links.items():

        logger.info(
            f"📦 Категория {category_id} | ссылок: {len(urls)}"
        )

        for url in urls:
            tasks.append(
                asyncio.create_task(
                    worker(url, category_id)
                )
            )

    await asyncio.gather(*tasks)

    await session.close()

    logger.info("✅ Парсинг завершён")


async def run_free_parser():

    session = WBSession()
    await session.start()

    semaphore = asyncio.Semaphore(3)

    async def worker(url, category_id):

        async with semaphore:
            try:
                logger.info(
                    f"🔗 Парсинг {category_id}: {url}"
                )

                await parse_single_url(
                    session,
                    url,
                    category_id
                )

            except Exception:
                logger.exception("❌ Ошибка парсинга")

    tasks = []

    for category_id, urls in free_pars_links.items():

        logger.info(
            f"📦 Категория {category_id} | ссылок: {len(urls)}"
        )

        for url in urls:
            tasks.append(
                asyncio.create_task(
                    worker(url, category_id)
                )
            )

    await asyncio.gather(*tasks)

    await session.close()

    logger.info("✅ Парсинг завершён")


import math
from datetime import datetime, timezone, UTC
from playwright.async_api import async_playwright
from core.logger import parser_logger
from mongo_db.models import WBProductRaw
import asyncio
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import hashlib
import json
from parser.links import pars_links

logger = parser_logger


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

async def fetch_catalog_page(context, base_url, page, max_retries=5):
    url = set_page(base_url, page)

    for attempt in range(max_retries):
        try:
            response = await context.request.get(url, timeout=30_000)

            if response.status == 200:
                try:
                    return await response.json()
                except Exception as e:
                    logger.exception(f"❌ Ошибка парсинга JSON - {str(e)}")
                    return None

            logger.warning(
                f"⚠️ HTTP {response.status} | attempt {attempt+1}/{max_retries}"
            )

        except Exception as e:
            logger.exception(
                f"❌ Ошибка запроса | attempt {attempt+1}/{max_retries} - {str(e)}"
            )

        await asyncio.sleep(2 + attempt)

    return None


async def save_products(products: list, category_id: int):
    now = datetime.now(timezone.utc)

    inserted = 0
    updated = 0

    for p in products:
        try:
            nm_id = p.get("id")
            if not nm_id:
                continue

            existing = await WBProductRaw.find_one(
                WBProductRaw.nm_id == nm_id
            )

            doc = {
                "nm_id": nm_id,
                "data": p,
                "data_hash": calc_data_hash(p),
                "category_id": category_id,
                "fetched_at": now,
            }

            if existing:
                await existing.set(doc)
                updated += 1
            else:
                await WBProductRaw(**doc).insert()
                inserted += 1

        except Exception:
            logger.exception(f"❌ Ошибка сохранения nm_id={p.get('id')}")

    logger.info(f"DB: +{inserted} новых")


async def run_playwright_parser(api_url, category_id):
    browser = None

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

            total_pages = None
            page_num = 1

            while True:
                logger.info(f"📄 Загружаем page={page_num} из {total_pages}")

                data = await fetch_catalog_page(context, api_url, page_num)
                if not data:
                    break

                products = data.get("products", [])
                if not products:
                    break

                await save_products(products, category_id)

                if total_pages is None:
                    total = data.get("total", 0)
                    page_size = len(products)
                    total_pages = math.ceil(total / page_size)

                if page_num >= total_pages:
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



async def run_raw_parser():
    try:
        total = 0

        for category_id, urls in pars_links.items():
            logger.info(
                f"📦 Старт парсинга категории: {category_id} "
                f"(urls={len(urls)})"
            )

            for url in urls:
                logger.info(
                    f"🔗 Парсинг {category_id}: {url}"
                )

                await run_playwright_parser(url, category_id)
                total += 1

                await asyncio.sleep(10)  # антибан

        logger.info(f"✅ Парсинг завершён, всего запусков: {total}")

    except Exception:
        logger.exception("🔥 Критическая ошибка парсера товаров")








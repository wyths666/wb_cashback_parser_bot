import asyncio
import random
from datetime import datetime, timedelta, UTC
from typing import List, Dict, Iterable, Tuple
from enum import Enum
from playwright.async_api import async_playwright
from core.logger import parser_logger
from core.mongo import init_database
from mongo_db.models import WBProductFiltered

logger = parser_logger

URL = "https://www.wildberries.ru/__internal/card/cards/v4/detail?appType=1&curr=rub&dest=-1257484&spp=30&hide_vflags=4294967296&hide_dtype=9&ab_testing=false&lang=ru"
CONCURRENCY = 2
DELAY_MIN = 2.5   # сек
DELAY_MAX = 4.5   # сек

async def init_wb_session(context):
    page = await context.new_page()

    async with page.expect_response(
        lambda r: "wildberries.ru" in r.url and r.status == 200,
        timeout=15000
    ):
        await page.goto("https://www.wildberries.ru", wait_until="networkidle")
        await asyncio.sleep(5)

    # небольшая страховка
    await page.wait_for_timeout(2000)

    await page.close()


class CashbackStatus(str, Enum):
    OK = "ok"
    NONE = "none"
    BLOCKED = "blocked"


async def fetch_feedback_points(request, nm_id) -> Tuple[int, CashbackStatus, int | None]:
    try:
        r = await request.get(URL, params={"nm": str(nm_id)})

        if r.status == 498:
            logger.warning(f"[BLOCKED 498] nm={nm_id}")
            return nm_id, CashbackStatus.BLOCKED, None

        if r.status != 200:
            logger.warning(f"[HTTP {r.status}] nm={nm_id}")
            return nm_id, CashbackStatus.NONE, None

        data = await r.json()

        products = data.get("products")
        if not products:
            return nm_id, CashbackStatus.NONE, None

        product = products[0]

        if product.get("id") != nm_id:
            return nm_id, CashbackStatus.NONE, None

        points = product.get("feedbackPoints")
        if points is None:
            return nm_id, CashbackStatus.NONE, None

        return nm_id, CashbackStatus.OK, points

    except Exception as e:
        logger.exception(f"[ERROR fetch_feedback_points] nm={nm_id}: {e}")
        return nm_id, CashbackStatus.NONE, None




async def main(nm_ids):
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
                "Chrome/143.0.0.0 Safari/537.36"
            ),
        )

        await init_wb_session(context)

        request = context.request
        sem = asyncio.Semaphore(CONCURRENCY)

        results = {}
        blocked = []
        unknown = []

        async def bound(nm):
            async with sem:
                return await fetch_feedback_points(request, nm)

        responses = await asyncio.gather(*(bound(nm) for nm in nm_ids))

        for nm, status, points in responses:
            if status == CashbackStatus.OK:
                results[nm] = points
            elif status == CashbackStatus.BLOCKED:
                blocked.append(nm)
            else:
                unknown.append(nm)

        await browser.close()

        return results, blocked, unknown


from pydantic import BaseModel

class NmOnly(BaseModel):
    nm_id: int

async def get_nm_ids():
    since = datetime.now(UTC) - timedelta(hours=48)

    docs = await WBProductFiltered.find(
        WBProductFiltered.published == True,
        WBProductFiltered.published_at >= since,
    ).project(NmOnly).to_list()

    return [doc.nm_id for doc in docs]

async def get_nm_ids_unpublished():
    docs = await WBProductFiltered.find(
        WBProductFiltered.published == False
    ).project(NmOnly).to_list()

    nm_ids = [doc.nm_id for doc in docs]
    return nm_ids

async def get_nm_ids_to_delete_unpublished():
    nm_ids = await get_nm_ids_unpublished()
    results, blocked, unknown = await main(nm_ids)

    logger.info(f"✅ cashback confirmed: {len(set(results))}")
    logger.warning(f"🚫 blocked (498): {len(set(blocked))}")
    logger.warning(f"❌ to delete: {len(set(unknown))}")

    return unknown

async def entrypoint():
    await init_database()
    nm_ids = await get_nm_ids_unpublished()

    results, blocked, unknown = await main(nm_ids)

    logger.info(f"✅ cashback confirmed: {len(set(results))}")
    logger.warning(f"🚫 blocked (498): {len(set(blocked))}")
    logger.warning(f"❌ to delete: {len(set(unknown))}")



async def get_nm_ids_to_delete():
    nm_ids = await get_nm_ids()
    results, blocked, unknown = await main(nm_ids)

    logger.info(f"✅ cashback confirmed: {len(set(results))}")
    logger.warning(f"🚫 blocked (498): {len(set(blocked))}")
    logger.warning(f"❌ to delete: {len(set(unknown))}")

    return unknown

if __name__ == "__main__":
    asyncio.run(entrypoint())


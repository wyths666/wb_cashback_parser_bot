from playwright.async_api import async_playwright
from pymongo import UpdateOne

from mongo_db.models import OzonProductRaw


class OzonParser:

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.request = None




    async def start(self):

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        self.context = await self.browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        page = await self.context.new_page()

        # получаем cookies ozon
        await page.goto("https://www.ozon.ru", wait_until="domcontentloaded")

        await page.wait_for_timeout(4000)

        await page.close()

        self.request = self.context.request

    async def close(self):

        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

    async def fetch_page(self, page, category_url):

        url = (
            "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
            f"?url={category_url}&page={page}&layout_page_index={page}"
        )




        r = await self.request.get(
            url,
            headers={
                "accept": "application/json",
                "x-o3-app-name": "ozonapp_web",
            },
        )
        if r.status != 200:
            return None

        try:
            return await r.json()
        except:
            return None

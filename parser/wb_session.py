import asyncio
from playwright.async_api import async_playwright
from core.logger import parser_logger

logger = parser_logger


class WBSession:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.request = None

        self.started = False
        self._restart_lock = asyncio.Lock()

    async def start(self):
        if self.started:
            return

        logger.info("🚀 Starting WB Playwright session")

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        await self._create_context()
        self.started = True

        logger.info("✅ WB session ready")

    async def _create_context(self):
        self.context = await self.browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/143.0.0.0 Safari/537.36"
            ),
        )

        await self._init_wb()
        self.request = self.context.request

    async def _init_wb(self):
        page = await self.context.new_page()
        await page.goto(
            "https://www.wildberries.ru",
            wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(2000)
        await asyncio.sleep(5)
        await page.close()

    async def restart(self):
        async with self._restart_lock:
            logger.warning("🔄 Restarting WB context")

            try:
                if self.context:
                    await self.context.close()
            except Exception:
                logger.exception("Error while closing WB context")

            await self._create_context()

            logger.info("✅ WB context restarted")

    async def close(self):
        logger.info("🛑 Shutting down WB session")

        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

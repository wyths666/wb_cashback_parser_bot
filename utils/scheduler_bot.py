import asyncio
from datetime import datetime, timedelta, UTC
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import os
import dotenv
from mongo_db.models import User
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from core.logger import scheduler_logger

dotenv.load_dotenv()
logger = scheduler_logger
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ACCESS_DAYS = 30


class Scheduler:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        self.parser_lock = asyncio.Lock()
        self.publish_lock = asyncio.Lock()

    def setup(self):
        # 09:00 — публикация
        self.scheduler.add_job(
            self.publish,
            CronTrigger(hour=9, minute=0),
            id="publish",
            replace_existing=True,
        )

        # Контроль доступа
        self.scheduler.add_job(
            self.validate_channel_access,
            CronTrigger(hour=11, minute=0),
            id="validate_channel_access",
            replace_existing=True,
        )

        # Удаление товаров без кэшбэка
        self.scheduler.add_job(
            self.delete_product,
            CronTrigger(hour=2, minute=0),
            id="delete_product",
            replace_existing=True,
        )



    async def start(self):
        self.scheduler.start()
        logger.info("⏰ Планировщик запущен")

    # ===== задачи =====

    async def publish(self):
        logger.info("⏳ publish ждёт lock")
        async with self.publish_lock:
            logger.info("🚀 Запуск публикатора")
            from bot.newsletter import PublishService

            service = PublishService(self.bot)
            await service.run()


    async def validate_channel_access(self):
        logger.info("🔐 Запуск проверки доступа к каналу")

        now = datetime.now(UTC)
        expire_border = now - timedelta(days=ACCESS_DAYS)

        users = await User.find(
            User.has_access == True,
            User.access_granted_at <= expire_border,
        ).to_list()

        logger.info(f"🔎 Найдено пользователей на удаление: {len(users)}")
        CHAT_OWNER_ID = 78429874
        for user in users:
            user_id = user.telegram_id

            # 🔒 если владелец канала — пропускаем
            if user_id == CHAT_OWNER_ID:
                logger.warning(f"👑 Пропуск владельца канала: {user_id}")
                continue

            try:
                # 🚫 удаляем из канала
                await self.bot.ban_chat_member(
                    chat_id=CHANNEL_ID,
                    user_id=user_id,
                )

                await self.bot.unban_chat_member(
                    chat_id=CHANNEL_ID,
                    user_id=user_id,
                )

                # 📩 уведомляем пользователя в ЛС
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "⛔️ У вас закончилась подписка на канал.\n\n"
                            "Чтобы снова получать выгодные предложения — отправьте /start\nИ оплатите доступ."
                        ),
                    )
                except TelegramForbiddenError:
                    logger.info(f"📭 ЛС закрыты: {user_id}")

                user.has_access = False
                user.access_granted_at = None
                await user.save()

                logger.info(f"❌ Доступ отозван: {user_id}")

            except TelegramBadRequest as e:
                text = str(e)

                if "PARTICIPANT_ID_INVALID" in text:
                    logger.info(f"ℹ️ Пользователь {user_id} уже не в канале")
                    user.has_access = False
                    user.access_granted_at = None
                    await user.save()

                elif "can't remove chat owner" in text:
                    logger.warning(f"👑 Нельзя удалить владельца: {user_id}")

                elif "not enough rights" in text:
                    logger.critical("❌ У бота нет прав администратора в канале")
                    break  # дальше смысла нет

                else:
                    logger.error(f"❌ TelegramBadRequest {user_id}: {text}")

            except TelegramForbiddenError:
                logger.info(f"🚫 Бот заблокирован пользователем {user_id}")

            except Exception:
                logger.exception(f"💥 Неожиданная ошибка при удалении {user_id}")


    async def delete_product(self):
        logger.info("⏳ delete_product ждёт lock")
        async with self.parser_lock:
            logger.info("🚀 Запуск валидатора кэшбэка")
            from bot.delete_service import DeleteService
            service = DeleteService(self.bot)
            await service.run()
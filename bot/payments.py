import json

from aiogram import Router, F
from aiogram.types import Message, LabeledPrice, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.types import PreCheckoutQuery
from datetime import datetime, timedelta, timezone
import os
import logging
from mongo_db.models import Payment, User

router = Router()
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
UTC = timezone.utc
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
logger = logging.getLogger(__name__)

# Получаем цену и конвертируем в копейки
try:
    price_str = os.getenv("PRICE_RUB", "149")
    PRICE_RUB = int(price_str)
    PRICE_IN_KOPECKS = PRICE_RUB * 100
except ValueError as e:
    logger.error(f"Ошибка парсинга цены: {e}")
    PRICE_RUB = 149
    PRICE_IN_KOPECKS = 100 * 100


@router.message(Command("start"))
async def buy(message: Message):
    try:
        logger.info(f"Создание инвойса. Сумма: {PRICE_RUB} руб.")

        price = LabeledPrice(
            label="Доступ к приватному каналу",
            amount=int(PRICE_IN_KOPECKS)
        )
        desc = """
        Ловец Кэшбэка WB ⭐

Закрытый доступ к максимальным кэшбэкам Wildberries за отзывы

💸 Как это работает:

Купи товар → оставь отзыв → получи официальный кэшбэк на WB-кошелёк

💰Иногда кэшбэк выше стоимости товара

🔥 Что внутри канала:

• Кэшбэки от 30% до 100+%

• Только актуальные предложения

• Ежедневные публикации более 100 товаров

• Экономия на каждой покупке

🔒 Подписка: 149 ₽ / месяц📩 Поддержка: @Lovecwbsupport"""

        await message.answer(desc)
        await message.answer_invoice(
            title="Доступ к приватному каналу",
            description="🔒 Подписка: 149 ₽ / месяц",
            payload=f"access:{message.from_user.id}",
            provider_token=PROVIDER_TOKEN,
            currency="RUB",
            prices=[price],
            start_parameter="buy-access",

            need_email=True,
            send_email_to_provider=True,

            provider_data=json.dumps({
                "receipt": {
                    "items": [
                        {
                            "description": "Подписка на закрытый Telegram-канал (1 месяц)",
                            "quantity": 1,
                            "amount": {
                                "value": f"{PRICE_RUB}.00",  # ← ВАЖНО
                                "currency": "RUB"
                            },
                            "vat_code": 1,
                            "payment_mode": "full_payment",
                            "payment_subject": "service"
                        }
                    ],
                    "tax_system_code": 2
                }
            }),

            need_name=False,
            need_phone_number=False,
            need_shipping_address=False,
            is_flexible=False,
        )

        logger.info(f"Инвойс создан для пользователя {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса: {e}")
        await message.answer("❌ Произошла ошибка при создании платежа. Пожалуйста, попробуйте позже.")


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    logger.info(f"Pre-checkout запрос от {pre_checkout.from_user.id}")
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    try:
        payment_data = message.successful_payment
        user_id = message.from_user.id

        logger.info(f"Успешный платеж от {user_id}, сумма: {payment_data.total_amount/100} {payment_data.currency}")

        # Детальное логирование данных платежа
        logger.info(f"Данные платежа: "
                    f"provider_payment_charge_id={payment_data.provider_payment_charge_id}, "
                    f"invoice_payload={payment_data.invoice_payload}, "
                    f"telegram_payment_charge_id={payment_data.telegram_payment_charge_id}")

        payment = Payment(
            telegram_id=user_id,
            provider_payment_charge_id=payment_data.provider_payment_charge_id,
            payload=payment_data.invoice_payload,
            amount=payment_data.total_amount,
            currency=payment_data.currency,
            paid_at=datetime.now(UTC)
        )

        await payment.insert()
        logger.info("Платеж сохранен в БД")

        user = await User.find_one(User.telegram_id == user_id)

        if user:
            if not user.has_access:
                user.has_access = True
                user.access_granted_at = datetime.now(UTC)
                await user.save()
                logger.info(f"Обновлен доступ для существующего пользователя {user_id}")
            else:
                logger.info(f"Пользователь {user_id} уже имеет доступ")
        else:
            new_user = User(
                telegram_id=user_id,
                username=message.from_user.username,
                has_access=True,
                access_granted_at=datetime.now(UTC),
                created_at=datetime.now(UTC)
            )
            await new_user.insert()
            logger.info(f"Создан новый пользователь: {new_user}")

        logger.info(f"Создание инвайт-ссылки для канала {CHANNEL_ID}")
        expire_date = datetime.now(UTC) + timedelta(hours=1)
        invite = await message.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(expire_date.timestamp()),
        )
        logger.info(f"Инвайт-ссылка создана: {invite.invite_link}")

        # 4️⃣ отправляем ссылку
        await message.answer(
            "✅ Оплата прошла успешно!\n\n"
            "🔐 Ваша ссылка для входа в канал:\n"
            f"<a href='{invite.invite_link}'>Нажмите здесь, чтобы присоединиться</a>\n\n"
            f"Или скопируйте ссылку:\n"
            f"<code>{invite.invite_link}</code>\n\n"
            "⚠️ Ссылка действует 1 час и только для одного пользователя.\n"
            "⚠️ Не передавайте ссылку другим пользователям.",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        logger.info(f"Ссылка отправлена пользователю {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке платежа: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке платежа.\n"
            "Пожалуйста, обратитесь к администратору @ваш_администратор"
        )
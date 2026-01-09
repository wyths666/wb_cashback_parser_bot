import logging
import motor.motor_asyncio
from datetime import datetime, timezone
import motor.motor_asyncio
from beanie import init_beanie
from mongo_db.models import get_document_models
import os
import dotenv
dotenv.load_dotenv()

MONGO_URL = f'mongodb://{os.getenv("MONGO_HOST")}:{os.getenv("MONGO_PORT")}/{os.getenv("MONGO_NAME")}'

logger = logging.getLogger(__name__)

async def init_database():
    """Инициализация подключения к MongoDB"""
    mongo_url = MONGO_URL
    db_name = "wb_parser_bot"

    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    database = client[db_name]
    await init_beanie(
        database=client[db_name],
        document_models=get_document_models()
    )
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()

    logger.info(
        "🕒 Время сервера | UTC: %s | Local: %s",
        now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        now_local.strftime("%Y-%m-%d %H:%M:%S")
    )

    # 📦 Количество документов в каждой коллекции
    logger.info("📊 Статистика MongoDB:")

    collections = await database.list_collection_names()

    for collection_name in collections:
        count = await database[collection_name].count_documents({})
        logger.info("   • %s: %d документов", collection_name, count)
    logger.info(f"✅ MongoDB подключен к базе '{db_name}'")
    return client
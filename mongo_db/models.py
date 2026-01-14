from beanie import Document, before_event, Insert
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC

from pydantic import Field
from pymongo import IndexModel


class WBProductRaw(Document):
    nm_id: int
    data: Dict[str, Any]
    category_id: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_hash: Optional[str] = None

    @before_event(Insert)
    def set_created_at(self):
        self.fetched_at = datetime.now(UTC)

    class Settings:
        name = "wb_products_raw"
        indexes = [
            "nm_id"
        ]

class WBProductFiltered(Document):
    nm_id: int

    cashback_percent: float
    price: float
    cashback: int
    source_hash: Optional[str] = None
    category_id: str

    # публикация
    published: bool = False
    published_at: Optional[datetime] = None
    telegram_message_ids: Optional[List[int]] = None
    published_free: Optional[bool] = None
    published_free_at: Optional[datetime] = None
    published_free_message_ids: Optional[List[int]] = None
    # фото
    photos_parsed: bool = False
    photos: List[str] = []

    reserved_for_photos: bool = False
    reserved_for_photos_at: Optional[datetime] = None

    # логистика
    fulfillment: str              # FBO / LIKELY_FBO
    fulfillment_score: int        # 0–4

    # сырые данные
    data: dict

    filtered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event(Insert)
    def set_filtered_at(self):
        self.filtered_at = datetime.now(UTC)

    class Settings:
        name = "wb_products_filtered"
        indexes = [
            IndexModel(
                [("nm_id", 1)],
                unique=True,
                name="nm_id_1",
            ),
            "category_id",
            "published",
            "published_free",
            "source_hash",
            "photos_parsed",
            "reserved_for_photos",
            [("category_id", 1), ("photos_parsed", 1), ("published", 1)],
            [("reserved_for_photos", 1), ("reserved_for_photos_at", 1)],
        ]

class User(Document):
    telegram_id: int
    username: Optional[str] = None

    has_access: bool = False
    access_granted_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "users"
        indexes = [
            "telegram_id",
            "has_access",
        ]

class Payment(Document):
    telegram_id: int

    provider: str = "telegram_yookassa"
    provider_payment_charge_id: str

    payload: str

    amount: int  # в копейках
    currency: str = "RUB"

    paid_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "payments"
        indexes = [
            "telegram_id",
            "provider_payment_charge_id",
            "paid_at",
        ]

def get_document_models():
    return [WBProductRaw, WBProductFiltered, User, Payment]
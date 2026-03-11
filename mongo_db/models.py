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
            "nm_id",
            "data.reviewRating",
            "data.feedbacks"
        ]

class OzonProductRaw(Document):
    sku: str
    title: str
    original_price: Optional[int] = None
    price: int
    discount: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    brand: Optional[str] = None
    stock: Optional[int] = None
    images: List[str] = Field(default_factory=list)
    url: str
    category: str
    parent_category: str
    review_points: Optional[int] = None

    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event(Insert)
    def set_created_at(self):
        self.fetched_at = datetime.now(UTC)

    class Settings:
        name = "ozon_products_raw"
        indexes = [
            IndexModel([("sku", 1)], unique=True),
            "price",
            "original_price",
            "review_points"
        ]

class OzonProductFiltered(Document):
    sku: str
    title: str
    original_price: Optional[int] = None
    price: int
    discount: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    brand: Optional[str] = None
    stock: Optional[int] = None
    images: List[str] = Field(default_factory=list)
    url: str
    category: str
    parent_category: str
    review_points: Optional[int] = None

    published: bool = False
    published_at: Optional[datetime] = None
    telegram_message_ids: Optional[list[int]] = None

    filtered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event(Insert)
    def set_filtered_at(self):
        self.filtered_at = datetime.now(UTC)

    class Settings:
        name = "ozon_products_filtered"
        indexes = [
            IndexModel([("sku", 1)], unique=True),
            "price",
            "original_price",
            "review_points",
            "published",
            "filtered_at"
        ]


class OzonProductFilteredWithPoints(Document):
    sku: str
    title: str
    original_price: Optional[int] = None
    price: int
    discount: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    brand: Optional[str] = None
    stock: Optional[int] = None
    images: List[str] = Field(default_factory=list)
    url: str
    category: str
    parent_category: str
    review_points: Optional[int] = None

    published: bool = False
    published_at: Optional[datetime] = None
    telegram_message_ids: Optional[list[int]] = None

    filtered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event(Insert)
    def set_filtered_at(self):
        self.filtered_at = datetime.now(UTC)

    class Settings:
        name = "ozon_products_filtered_withs_points"
        indexes = [
            IndexModel([("sku", 1)], unique=True),
            "price",
            "original_price",
            "review_points",
            "published",
            "filtered_at"
        ]


class WBProductDiscount(Document):

    nm_id: int
    category_id: str

    price: float
    basic_price: float
    discount_percent: float

    rating: float
    feedbacks: int

    data: Dict[str, Any]

    source_hash: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    photos_parsed: bool = False
    photos: List[str] = []

    reserved_for_photos: bool = False
    reserved_for_photos_at: Optional[datetime] = None

    published: bool = False
    published_at: Optional[datetime] = None
    telegram_message_ids: Optional[list[int]] = None

    class Settings:
        name = "wb_products_discount"

        indexes = [
            "nm_id",
            "discount_percent",
            "price",
            "rating"
        ]


class ParserSettings(Document):
    key: str
    category_index: int = 0
    chat_category_index: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chat_updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "parser_settings"
        indexes = ["key"]


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
            IndexModel(
                [
                    ("category_id", 1),
                    ("published", 1),
                    ("photos_parsed", 1),
                    ("filtered_at", -1),
                    ("cashback_percent", -1),
                ],
                name="publish_pool_sort_idx",
            )
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
    return [WBProductRaw, WBProductFiltered, User, Payment, WBProductDiscount, ParserSettings, OzonProductRaw, OzonProductFilteredWithPoints, OzonProductFiltered]
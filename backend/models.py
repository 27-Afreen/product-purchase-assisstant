from typing import Optional, List
from pydantic import BaseModel


class Product(BaseModel):
    id: int
    name: str
    category: str
    brand: str
    price: float
    rating: float
    platform: str
    link: Optional[str] = None


class PlatformOffer(BaseModel):
    product_id: int
    platform: str
    price: float
    delivery_days: Optional[int] = None
    return_days: Optional[int] = None
    warranty_months: Optional[int] = None
    seller_score: Optional[float] = None


class Review(BaseModel):
    product_id: int
    rating: float
    review_text: str
    sentiment_score: Optional[float] = None


class Recommendation(BaseModel):
    best_product: Product
    alternatives: List[Product]
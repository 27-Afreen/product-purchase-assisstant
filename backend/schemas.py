from typing import List
from pydantic import BaseModel

from models import Product


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    matched_category: str | None = None
    matched_platforms: List[str] = []
    recommendations: List[Product] = []
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import Product
from schemas import ChatRequest, ChatResponse
from services.recommendation_service import generate_recommendation
from repositories.product_repository import get_all_products, search_products

app = FastAPI(title="Product Purchase Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Backend is running successfully"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/products", response_model=list[Product])
def list_products():
    return get_all_products()


@app.get("/products/search", response_model=list[Product])
def search_products_api(
    category: str | None = None,
    platform: str | None = None,
    max_price: float | None = None,
):
    return search_products(
        category=category,
        platform=platform,
        max_price=max_price,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    result = generate_recommendation(request.message)

    return ChatResponse(
        reply=result["reply"],
        matched_category=result["matched_category"],
        matched_platforms=result["matched_platforms"],
        recommendations=result["recommendations"],
    )
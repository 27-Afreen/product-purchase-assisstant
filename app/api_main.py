from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from pathlib import Path
import re

app = FastAPI(title="Product Purchase Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str


def extract_budget(query):
    query = query.lower()

    under_match = re.search(r'under\s*\$?\s*(\d+)', query)
    if under_match:
        return 0.0, float(under_match.group(1))

    between_match = re.search(r'between\s*\$?\s*(\d+)\s*and\s*\$?\s*(\d+)', query)
    if between_match:
        return float(between_match.group(1)), float(between_match.group(2))

    return None, None


def extract_domain(query):
    query = query.lower()

    skincare_words = [
        "cleanser", "serum", "moisturizer", "moisturiser",
        "skincare", "pigmentation", "acne", "redness", "hydration"
    ]

    appliance_words = [
        "smart tv", "tv", "microwave", "vacuum",
        "vacuum cleaner", "appliance", "pet hair",
        "heating", "suction", "picture quality"
    ]

    if any(word in query for word in skincare_words):
        return "Skincare"
    if any(word in query for word in appliance_words):
        return "Home Appliance"
    return None


def extract_category(query):
    query = query.lower()

    category_map = {
        "cleanser": "Cleanser",
        "face wash": "Cleanser",
        "facewash": "Cleanser",
        "serum": "Serum",
        "moisturizer": "Moisturizer",
        "moisturiser": "Moisturizer",
        "cream": "Moisturizer",
        "smart tv": "Smart TV",
        "tv": "Smart TV",
        "microwave": "Microwave",
        "vacuum cleaner": "Vacuum Cleaner",
        "vacuum": "Vacuum Cleaner"
    }

    for key, value in category_map.items():
        if key in query:
            return value

    return None


def extract_platforms(query):
    query = query.lower()

    platform_map = {
        "yesstyle": "YesStyle",
        "ulta": "Ulta Beauty",
        "amazon": "Amazon",
        "walmart": "Walmart",
        "target": "Target",
        "costco": "Costco",
        "walgreens": "Walgreens"
    }

    found = []
    for key, value in platform_map.items():
        if key in query and value not in found:
            found.append(value)

    return found


def extract_skin_types(query):
    query = query.lower()

    skin_map = {
        "oily": "Oily",
        "dry": "Dry",
        "combination": "Combination",
        "sensitive": "Sensitive",
        "normal": "Normal"
    }

    found = []
    for key, value in skin_map.items():
        if key in query and value not in found:
            found.append(value)

    return found


def extract_needs(query):
    query = query.lower()

    need_map = {
        "acne": "Acne",
        "pimple": "Acne",
        "breakout": "Acne",
        "pigmentation": "Pigmentation",
        "dark spots": "Pigmentation",
        "glow": "Dullness",
        "dullness": "Dullness",
        "redness": "Redness",
        "barrier": "Barrier repair",
        "repair": "Barrier repair",
        "hydration": "Hydration",
        "hydrating": "Hydration",
        "oil": "Oil control",
        "picture quality": "Picture quality",
        "sound": "Sound quality",
        "pet hair": "Pet hair cleaning",
        "suction": "Suction power",
        "heating": "Heating performance",
        "easy to use": "Ease of use",
        "value": "Value",
        "reliable": "Reliability",
        "reliability": "Reliability",
        "durable": "Durability",
        "durability": "Durability"
    }

    found = []
    for key, value in need_map.items():
        if key in query and value not in found:
            found.append(value)

    return found


def compute_quality_score(row):
    rating = float(row["rating_avg"])
    sentiment = float(row["avg_sentiment_score"])
    reviews = float(row["review_count"])

    review_factor = min(reviews / 1000, 1.0)

    quality = (rating * 0.5) + (sentiment * 5 * 0.3) + (review_factor * 0.2)
    return round(quality, 4)


def score_product(row, category, platforms, skin_types, needs, budget_low, budget_high):
    score = 0.0

    score += float(row["quality_score"]) * 0.5

    if category and str(row["subcategory"]).lower() == category.lower():
        score += 2.0

    if platforms and str(row["platform"]).lower() in [p.lower() for p in platforms]:
        score += 1.5

    price = float(row["price_discounted"])
    if budget_high is not None:
        if budget_low is not None and budget_low <= price <= budget_high:
            score += 1.5
        elif budget_low == 0.0 and price <= budget_high:
            score += 1.5

    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            score += 1.0

    row_needs = str(row["target_concerns_or_use_cases"]).lower()
    for need in needs:
        if need.lower() in row_needs:
            score += 1.2

    return round(score, 4)


def compute_best_overall_score(row):
    return round((float(row["quality_score"]) * 0.8) + (float(row["rating_avg"]) * 0.2), 4)


def load_data():
    products_file = Path("data/raw/products_master.csv")
    sentiment_file = Path("data/processed/sentiment_master.csv")

    products_df = pd.read_csv(products_file)
    sentiment_df = pd.read_csv(sentiment_file)

    products_df.columns = products_df.columns.str.strip()
    sentiment_df.columns = sentiment_df.columns.str.strip()

    avg_sentiment = (
        sentiment_df.groupby("product_id")["sentiment_score"]
        .mean()
        .reset_index()
        .rename(columns={"sentiment_score": "avg_sentiment_score"})
    )

    df = products_df.merge(avg_sentiment, on="product_id", how="left")
    df["avg_sentiment_score"] = df["avg_sentiment_score"].fillna(0)
    df["quality_score"] = df.apply(compute_quality_score, axis=1)

    return df


@app.get("/")
def home():
    return {"message": "Product Purchase Assistant API is running"}


@app.post("/recommend")
def recommend_products(request: QueryRequest):
    df = load_data()
    user_query = request.query.strip()

    domain = extract_domain(user_query)
    category = extract_category(user_query)
    platforms = extract_platforms(user_query)
    skin_types = extract_skin_types(user_query)
    needs = extract_needs(user_query)
    budget_low, budget_high = extract_budget(user_query)

    if not any([
        domain,
        category,
        platforms,
        skin_types,
        needs,
        budget_high is not None
    ]):
        return {
            "query": user_query,
            "message": "Please provide a more specific query. Example: 'best smart tv under 1000' or 'best serum for pigmentation under 20 on yesstyle'."
        }

    filtered = df.copy()

    if domain:
        filtered = filtered[filtered["domain"].str.lower() == domain.lower()]

    if category:
        filtered = filtered[filtered["subcategory"].str.lower() == category.lower()]

    if platforms:
        filtered = filtered[
            filtered["platform"].str.lower().isin([p.lower() for p in platforms])
        ]

    if budget_high is not None:
        if budget_low is not None and budget_low > 0:
            filtered = filtered[
                (filtered["price_discounted"] >= budget_low) &
                (filtered["price_discounted"] <= budget_high)
            ]
        else:
            filtered = filtered[filtered["price_discounted"] <= budget_high]

    if filtered.empty:
        return {
            "query": user_query,
            "message": "No matching products found."
        }

    filtered = filtered.copy()

    filtered["match_score"] = filtered.apply(
        lambda row: score_product(
            row, category, platforms, skin_types, needs, budget_low, budget_high
        ),
        axis=1
    )

    filtered["best_overall_score"] = filtered.apply(compute_best_overall_score, axis=1)

    best_for_need = filtered.sort_values(by="match_score", ascending=False).iloc[0]
    best_overall = filtered.sort_values(by="best_overall_score", ascending=False).iloc[0]
    top_matches = filtered.sort_values(by="match_score", ascending=False).head(3)

    return {
        "query": user_query,
        "detected_preferences": {
            "domain": domain,
            "category": category,
            "platforms": platforms,
            "skin_types": skin_types,
            "needs": needs,
            "budget_low": budget_low,
            "budget_high": budget_high
        },
        "best_for_need": {
            "product_name": best_for_need["product_name"],
            "brand": best_for_need["brand"],
            "platform": best_for_need["platform"],
            "domain": best_for_need["domain"],
            "category": best_for_need["subcategory"],
            "price": float(best_for_need["price_discounted"]),
            "rating": float(best_for_need["rating_avg"]),
            "review_count": int(best_for_need["review_count"]),
            "sentiment_score": float(best_for_need["avg_sentiment_score"]),
            "quality_score": float(best_for_need["quality_score"]),
            "match_score": float(best_for_need["match_score"]),
            "use_cases": best_for_need["target_concerns_or_use_cases"]
        },
        "best_overall": {
            "product_name": best_overall["product_name"],
            "brand": best_overall["brand"],
            "platform": best_overall["platform"],
            "domain": best_overall["domain"],
            "category": best_overall["subcategory"],
            "price": float(best_overall["price_discounted"]),
            "rating": float(best_overall["rating_avg"]),
            "review_count": int(best_overall["review_count"]),
            "sentiment_score": float(best_overall["avg_sentiment_score"]),
            "quality_score": float(best_overall["quality_score"]),
            "overall_score": float(best_overall["best_overall_score"]),
            "use_cases": best_overall["target_concerns_or_use_cases"]
        },
        "top_matches": top_matches[[
            "product_name",
            "brand",
            "platform",
            "domain",
            "subcategory",
            "price_discounted",
            "rating_avg",
            "review_count",
            "avg_sentiment_score",
            "quality_score",
            "match_score"
        ]].to_dict(orient="records")
    }
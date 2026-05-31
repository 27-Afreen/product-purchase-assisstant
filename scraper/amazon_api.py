import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RAPIDAPI_KEY")

def search_products(query, budget=None):
    if not API_KEY:
        print("RAPIDAPI_KEY not set - returning mock data")
        return get_mock_products(query)

    url = "https://real-time-amazon-data.p.rapidapi.com/search"

    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "real-time-amazon-data.p.rapidapi.com"
    }

    params = {
        "query": query,
        "page": "1",
        "country": "US"
    }

    # Narrow the returned pool to items near the user's budget
    if budget and budget > 30:
        params["max_price"] = int(budget)
        if budget > 80:
            params["min_price"] = int(budget * 0.35)

    response = requests.get(url, headers=headers, params=params, timeout=30)
    data = response.json()

    # Quota exceeded or API error — fall back to mock data
    if "message" in data:
        print(f"API error: {data['message']} - returning mock data")
        return get_mock_products(query)

    products = []
    for item in data.get("data", {}).get("products", [])[:8]:
        title = str(item.get("product_title") or "").strip()
        if not title:
            continue
        # Normalise review count — API may return int or formatted string like "1,234"
        raw_reviews = item.get("product_num_ratings") or item.get("product_num_reviews") or 0
        try:
            num_reviews = int(str(raw_reviews).replace(",", "").replace(".", ""))
        except (ValueError, TypeError):
            num_reviews = 0

        # Try multiple price fields — the API sometimes omits product_price
        # for items with complex pricing (e.g. buy-box suppressed, bundles)
        raw_price = (
            item.get("product_price")
            or item.get("product_minimum_price")
            or item.get("product_buybox_price")
            or item.get("price")
            or item.get("min_price")
            or item.get("sale_price")
        )
        raw_original = (
            item.get("product_original_price")
            or item.get("product_list_price")
            or item.get("list_price")
            or item.get("was_price")
        )

        products.append({
            "name": title,
            "rating": item.get("product_star_rating", 0),
            "num_reviews": num_reviews,
            "price": raw_price,
            "original_price": raw_original,
            "link": item.get("product_url"),
            "image": item.get("product_photo") or item.get("product_image"),
            "asin": item.get("asin") or item.get("product_id"),
            "source": "Amazon"
        })

    return products


def get_mock_products(query):
    """Fallback sample data used when the API quota is exceeded or key is missing."""
    return [
        {"name": f"Sample Product A - {query}", "rating": 4.5, "num_reviews": 8420, "price": "$29.99", "original_price": "$39.99", "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product B - {query}", "rating": 4.2, "num_reviews": 3100, "price": "$49.99", "original_price": None,      "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product C - {query}", "rating": 4.0, "num_reviews": 950,  "price": "$39.99", "original_price": "$54.99",  "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product D - {query}", "rating": 3.8, "num_reviews": 210,  "price": "$24.99", "original_price": None,      "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product E - {query}", "rating": 3.5, "num_reviews": 45,   "price": "$19.99", "original_price": "$25.99",  "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product F - {query}", "rating": 3.4, "num_reviews": 32,   "price": "$34.99", "original_price": None,      "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product G - {query}", "rating": 4.3, "num_reviews": 5870, "price": "$44.99", "original_price": "$59.99",  "link": "#", "image": None, "source": "Amazon"},
        {"name": f"Sample Product H - {query}", "rating": 4.1, "num_reviews": 2240, "price": "$32.99", "original_price": None,      "link": "#", "image": None, "source": "Amazon"},
    ]

import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENWEBNINJA_KEY")

def normalize_price(raw) -> str:
    """Ensure price is always a USD-formatted string like $1,234.56."""
    if raw is None:
        return "N/A"
    s = str(raw).strip()
    if not s or s.upper() == "N/A":
        return "N/A"
    if s.startswith("$"):
        return s
    try:
        return f"${float(s.replace(',', '')):,.2f}"
    except (ValueError, TypeError):
        return s


def search_walmart_products(query: str, budget=None):
    if not API_KEY:
        print("OPENWEBNINJA_KEY not set - skipping Walmart search")
        return []

    url = "https://api.openwebninja.com/real-time-walmart-data/search"

    headers = {
        "x-api-key": API_KEY,
        "Accept": "*/*"
    }

    params = {
        "query": query,
        "page": 1,
        "sort_by": "best_match"
    }

    # Narrow the returned pool to items near the user's budget
    if budget and budget > 30:
        params["max_price"] = int(budget)
        if budget > 80:
            params["min_price"] = int(budget * 0.35)

    response = requests.get(url, headers=headers, params=params, timeout=30)

    if response.status_code != 200:
        print("Walmart API Error:", response.text)
        return []

    data = response.json()
    products_raw = data.get("data", {}).get("products", [])

    products = []
    for item in products_raw[:8]:
        title = str(item.get("title") or "").strip()
        if not title or title.upper() == "N/A":
            continue

        raw_reviews = item.get("num_reviews") or item.get("review_count") or 0
        try:
            num_reviews = int(str(raw_reviews).replace(",", "").replace(".", ""))
        except (ValueError, TypeError):
            num_reviews = 0

        products.append({
            "name": title,
            "rating": item.get("rating", 0) or 0,
            "num_reviews": num_reviews,
            "price": normalize_price(item.get("price")),
            "original_price": normalize_price(
                item.get("was_price")
                or item.get("list_price")
                or item.get("regular_price")
                or item.get("original_price")
            ),
            "link": build_walmart_link(item),
            "image": (
                item.get("image")
                or item.get("image_url")
                or item.get("thumbnail")
                or item.get("thumbnail_url")
                or item.get("primary_image_url")
            ),
            "product_id": item.get("product_id"),
            "us_item_id": item.get("us_item_id"),
            "source": "Walmart"
        })

    return products


def build_walmart_link(item: dict) -> str:
    product_id = item.get("product_id")
    us_item_id = item.get("us_item_id")

    if us_item_id:
        return f"https://www.walmart.com/ip/{us_item_id}"
    if product_id:
        return f"https://www.walmart.com/ip/{product_id}"
    return "#"


if __name__ == "__main__":
    results = search_walmart_products("55 inch TV")
    for p in results:
        print(p)

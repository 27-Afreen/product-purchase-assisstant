import re

from repositories.product_repository import search_products


CATEGORIES = [
    "smart tv",
    "microwave",
    "cleanser",
    "serum",
]

PLATFORMS = [
    "amazon",
    "walmart",
    "target",
    "walgreens",
    "yesstyle",
]


def detect_category(message: str):
    text = message.lower()

    for category in CATEGORIES:
        if category in text:
            return category

    return None


def detect_platform(message: str):
    text = message.lower()

    for platform in PLATFORMS:
        if platform in text:
            return platform.title()

    return None


def detect_max_price(message: str):
    text = message.lower()

    patterns = [
        r"under\s+\$?(\d+)",
        r"below\s+\$?(\d+)",
        r"less than\s+\$?(\d+)",
        r"upto\s+\$?(\d+)",
        r"up to\s+\$?(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))

    return None


def generate_recommendation(message: str):
    matched_category = detect_category(message)
    matched_platform = detect_platform(message)
    max_price = detect_max_price(message)

    recommendations = search_products(
        category=matched_category,
        platform=matched_platform,
        max_price=max_price
    )

    if not recommendations and matched_category:
        recommendations = search_products(
            category=matched_category,
            max_price=max_price
        )

    if recommendations:
        best_product = max(recommendations, key=lambda product: product.rating)

        price_text = f" under ${max_price:.0f}" if max_price is not None else ""

        reply = (
            f"I found {len(recommendations)} product(s){price_text}. "
            f"Best match: {best_product.name} from {best_product.platform} "
            f"for ${best_product.price} with rating {best_product.rating}."
        )
    else:
        reply = "Sorry, I could not find matching products in the sample data."

    return {
        "reply": reply,
        "matched_category": matched_category,
        "matched_platforms": [matched_platform] if matched_platform else [],
        "recommendations": recommendations,
    }
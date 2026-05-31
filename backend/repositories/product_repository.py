from data.sample_products import products


def get_all_products():
    return products


def get_products_by_category(category: str):
    category = category.strip().lower()
    return [product for product in products if product.category.lower() == category]


def get_products_by_platform(platform: str):
    platform = platform.strip().lower()
    return [product for product in products if product.platform.lower() == platform]


def search_products(
    category: str | None = None,
    platform: str | None = None,
    max_price: float | None = None
):
    results = products

    if category:
        category = category.strip().lower()
        results = [
            product for product in results
            if product.category.lower() == category
        ]

    if platform:
        platform = platform.strip().lower()
        results = [
            product for product in results
            if product.platform.lower() == platform
        ]

    if max_price is not None:
        results = [
            product for product in results
            if product.price <= max_price
        ]

    return results
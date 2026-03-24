import pandas as pd
from pathlib import Path
import re

def extract_budget(query):
    match = re.search(r'under \$?(\d+)', query.lower())
    if match:
        return float(match.group(1))
    return None

def extract_category(query):
    query = query.lower()
    if "cleanser" in query:
        return "Cleanser"
    if "serum" in query:
        return "Serum"
    if "moisturizer" in query or "moisturiser" in query:
        return "Moisturizer"
    return None

def extract_concern(query):
    query = query.lower()
    concerns = {
        "acne": "Acne",
        "pigmentation": "Pigmentation",
        "glow": "Dullness",
        "sensitive": "Redness",
        "dry": "Barrier repair",
        "oil": "Oil control"
    }
    for key, value in concerns.items():
        if key in query:
            return value
    return None

def main():
    products_file = Path("data/raw/yesstyle_products.csv")
    sentiment_file = Path("data/processed/yesstyle_sentiment.csv")

    products_df = pd.read_csv(products_file)
    sentiment_df = pd.read_csv(sentiment_file)

    avg_sentiment = (
        sentiment_df.groupby("product_id")["sentiment_score"]
        .mean()
        .reset_index()
        .rename(columns={"sentiment_score": "avg_sentiment_score"})
    )

    df = products_df.merge(avg_sentiment, on="product_id", how="left")
    df["avg_sentiment_score"] = df["avg_sentiment_score"].fillna(0)

    user_query = input("Enter your skincare query: ")

    budget = extract_budget(user_query)
    category = extract_category(user_query)
    concern = extract_concern(user_query)

    filtered = df.copy()

    if category:
        filtered = filtered[filtered["subcategory"].str.lower() == category.lower()]

    if budget is not None:
        filtered = filtered[filtered["price_discounted"] <= budget]

    if concern:
        filtered = filtered[
            filtered["target_concerns"].str.lower().str.contains(concern.lower(), na=False)
        ]

    if filtered.empty:
        print("\nNo matching products found.")
        return

    filtered["score"] = (
        filtered["rating_avg"] * 0.6 +
        filtered["avg_sentiment_score"] * 5 * 0.4
    )

    filtered = filtered.sort_values(by="score", ascending=False)

    best = filtered.iloc[0]

    print("\nBest recommendation for your query:\n")
    print(f"Product Name   : {best['product_name']}")
    print(f"Brand          : {best['brand']}")
    print(f"Category       : {best['subcategory']}")
    print(f"Price          : ${best['price_discounted']}")
    print(f"Rating         : {best['rating_avg']}")
    print(f"Concern Match  : {best['target_concerns']}")
    print(f"Sentiment Score: {best['avg_sentiment_score']:.2f}")
    print("Why Recommended: Strong rating + positive review sentiment + query match")

    print("\nTop matching products:\n")
    print(filtered[[
        "product_name",
        "brand",
        "subcategory",
        "price_discounted",
        "rating_avg",
        "target_concerns",
        "avg_sentiment_score"
    ]].to_string(index=False))

if __name__ == "__main__":
    main()
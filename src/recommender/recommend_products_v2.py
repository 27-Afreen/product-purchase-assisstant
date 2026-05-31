import pandas as pd
from pathlib import Path
import re


def extract_budget(query):
    query = query.lower()

    under_match = re.search(r'under\s*\$?\s*(\d+)', query)
    if under_match:
        return 0.0, float(under_match.group(1))

    between_match = re.search(r'between\s*\$?\s*(\d+)\s*and\s*\$?\s*(\d+)', query)
    if between_match:
        low = float(between_match.group(1))
        high = float(between_match.group(2))
        return low, high

    return None, None


def extract_category(query):
    query = query.lower()

    category_map = {
        "cleanser": "Cleanser",
        "face wash": "Cleanser",
        "serum": "Serum",
        "moisturizer": "Moisturizer",
        "moisturiser": "Moisturizer",
        "cream": "Moisturizer",
    }

    for key, value in category_map.items():
        if key in query:
            return value

    return None


def extract_skin_type(query):
    query = query.lower()

    skin_type_map = {
        "oily": "Oily",
        "dry": "Dry",
        "combination": "Combination",
        "sensitive": "Sensitive",
        "normal": "Normal"
    }

    found_skin_types = []
    for key, value in skin_type_map.items():
        if key in query:
            found_skin_types.append(value)

    return found_skin_types


def extract_concerns(query):
    query = query.lower()

    concern_map = {
        "acne": "Acne",
        "pimple": "Acne",
        "breakout": "Acne",
        "oil": "Oil control",
        "oily": "Oil control",
        "pigmentation": "Pigmentation",
        "dark spots": "Pigmentation",
        "glow": "Dullness",
        "dullness": "Dullness",
        "redness": "Redness",
        "sensitive": "Redness",
        "barrier": "Barrier repair",
        "dry": "Barrier repair",
        "hydration": "Hydration",
        "hydrating": "Hydration",
    }

    found_concerns = []
    for key, value in concern_map.items():
        if key in query and value not in found_concerns:
            found_concerns.append(value)

    return found_concerns


def compute_best_for_need_score(row, budget_low, budget_high, category, skin_types, concerns):
    score = 0.0

    # Rating weight
    score += row["rating_avg"] * 0.35

    # Sentiment weight
    score += row["avg_sentiment_score"] * 5 * 0.20

    # Category match
    if category and str(row["subcategory"]).lower() == category.lower():
        score += 2.0

    # Budget match
    price = row["price_discounted"]
    if budget_high is not None:
        if budget_low is not None and budget_low <= price <= budget_high:
            score += 1.5
        elif budget_low == 0.0 and price <= budget_high:
            score += 1.5

    # Concern match
    row_concerns = str(row["target_concerns"]).lower()
    for concern in concerns:
        if concern.lower() in row_concerns:
            score += 1.2

    # Skin type match
    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            score += 1.0

    return score


def compute_best_overall_score(row):
    score = 0.0
    score += row["rating_avg"] * 0.7
    score += row["avg_sentiment_score"] * 5 * 0.3
    return score


def explain_recommendation(row, category, skin_types, concerns, budget_high):
    reasons = []

    reasons.append(f"high product rating ({row['rating_avg']})")
    reasons.append(f"positive review sentiment ({row['avg_sentiment_score']:.2f})")

    if category and str(row["subcategory"]).lower() == category.lower():
        reasons.append(f"matches your requested category ({category})")

    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            reasons.append(f"suits {skin.lower()} skin")

    row_concerns = str(row["target_concerns"]).lower()
    for concern in concerns:
        if concern.lower() in row_concerns:
            reasons.append(f"targets {concern.lower()}")

    if budget_high is not None and row["price_discounted"] <= budget_high:
        reasons.append(f"fits your budget under ${budget_high:.0f}")

    return ", ".join(reasons)


def main():
    products_file = Path("data/raw/yesstyle_products.csv")
    sentiment_file = Path("data/processed/yesstyle_sentiment.csv")

    if not products_file.exists():
        print("Missing file: data/raw/yesstyle_products.csv")
        return

    if not sentiment_file.exists():
        print("Missing file: data/processed/yesstyle_sentiment.csv")
        return

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

    user_query = input("Enter your skincare query: ").strip()

    budget_low, budget_high = extract_budget(user_query)
    category = extract_category(user_query)
    skin_types = extract_skin_type(user_query)
    concerns = extract_concerns(user_query)

    filtered = df.copy()

    if category:
        filtered = filtered[filtered["subcategory"].str.lower() == category.lower()]

    if budget_high is not None:
        if budget_low is not None:
            filtered = filtered[
                (filtered["price_discounted"] >= budget_low) &
                (filtered["price_discounted"] <= budget_high)
            ]
        else:
            filtered = filtered[filtered["price_discounted"] <= budget_high]

    if filtered.empty:
        print("\nNo matching products found after category/budget filtering.")
        return

    filtered = filtered.copy()

    filtered["best_for_need_score"] = filtered.apply(
        lambda row: compute_best_for_need_score(
            row, budget_low, budget_high, category, skin_types, concerns
        ),
        axis=1
    )

    filtered["best_overall_score"] = filtered.apply(
        compute_best_overall_score,
        axis=1
    )

    best_for_need = filtered.sort_values(by="best_for_need_score", ascending=False).iloc[0]
    best_overall = filtered.sort_values(by="best_overall_score", ascending=False).iloc[0]

    print("\n" + "=" * 70)
    print("SMART RECOMMENDER V2 RESULT")
    print("=" * 70)

    print("\nYour Query:")
    print(user_query)

    print("\nDetected Preferences:")
    print(f"Category   : {category if category else 'Not detected'}")
    print(f"Skin Type  : {', '.join(skin_types) if skin_types else 'Not detected'}")
    print(f"Concerns   : {', '.join(concerns) if concerns else 'Not detected'}")
    if budget_high is not None:
        if budget_low is not None and budget_low > 0:
            print(f"Budget     : ${budget_low:.0f} to ${budget_high:.0f}")
        else:
            print(f"Budget     : Under ${budget_high:.0f}")
    else:
        print("Budget     : Not detected")

    print("\n" + "-" * 70)
    print("BEST PRODUCT FOR YOUR NEED")
    print("-" * 70)
    print(f"Product Name   : {best_for_need['product_name']}")
    print(f"Brand          : {best_for_need['brand']}")
    print(f"Category       : {best_for_need['subcategory']}")
    print(f"Price          : ${best_for_need['price_discounted']}")
    print(f"Rating         : {best_for_need['rating_avg']}")
    print(f"Skin Type      : {best_for_need['skin_type']}")
    print(f"Concerns       : {best_for_need['target_concerns']}")
    print(f"Sentiment Score: {best_for_need['avg_sentiment_score']:.2f}")
    print(f"Match Score    : {best_for_need['best_for_need_score']:.2f}")
    print("Why Recommended:")
    print(explain_recommendation(best_for_need, category, skin_types, concerns, budget_high))

    print("\n" + "-" * 70)
    print("BEST OVERALL PRODUCT")
    print("-" * 70)
    print(f"Product Name   : {best_overall['product_name']}")
    print(f"Brand          : {best_overall['brand']}")
    print(f"Category       : {best_overall['subcategory']}")
    print(f"Price          : ${best_overall['price_discounted']}")
    print(f"Rating         : {best_overall['rating_avg']}")
    print(f"Skin Type      : {best_overall['skin_type']}")
    print(f"Concerns       : {best_overall['target_concerns']}")
    print(f"Sentiment Score: {best_overall['avg_sentiment_score']:.2f}")
    print(f"Overall Score  : {best_overall['best_overall_score']:.2f}")

    print("\n" + "-" * 70)
    print("TOP MATCHING PRODUCTS")
    print("-" * 70)
    display_cols = [
        "product_name",
        "brand",
        "subcategory",
        "price_discounted",
        "rating_avg",
        "skin_type",
        "target_concerns",
        "avg_sentiment_score",
        "best_for_need_score",
        "best_overall_score"
    ]
    print(
        filtered.sort_values(by="best_for_need_score", ascending=False)[display_cols]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
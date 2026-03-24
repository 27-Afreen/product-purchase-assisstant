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
        "facewash": "Cleanser",
        "serum": "Serum",
        "moisturizer": "Moisturizer",
        "moisturiser": "Moisturizer",
        "cream": "Moisturizer",
    }

    for key, value in category_map.items():
        if key in query:
            return value

    return None


def extract_skin_types(query):
    query = query.lower()

    skin_type_map = {
        "oily": "Oily",
        "dry": "Dry",
        "combination": "Combination",
        "sensitive": "Sensitive",
        "normal": "Normal"
    }

    found = []
    for key, value in skin_type_map.items():
        if key in query and value not in found:
            found.append(value)

    return found


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
        "spots": "Pigmentation",
        "glow": "Dullness",
        "dullness": "Dullness",
        "redness": "Redness",
        "barrier": "Barrier repair",
        "repair": "Barrier repair",
        "dryness": "Barrier repair",
        "dry": "Barrier repair",
        "hydration": "Hydration",
        "hydrating": "Hydration",
        "sensitive": "Redness",
    }

    found = []
    for key, value in concern_map.items():
        if key in query and value not in found:
            found.append(value)

    return found


def extract_platforms(query):
    query = query.lower()

    platform_map = {
        "yesstyle": "YesStyle",
        "amazon": "Amazon",
        "walmart": "Walmart",
        "target": "Target",
        "ulta": "Ulta Beauty",
        "walgreens": "Walgreens",
        "costco": "Costco"
    }

    found = []
    for key, value in platform_map.items():
        if key in query and value not in found:
            found.append(value)

    return found


def score_product(row, budget_low, budget_high, category, skin_types, concerns, platforms):
    score = 0.0

    # base rating + sentiment
    score += row["rating_avg"] * 0.35
    score += row["avg_sentiment_score"] * 5 * 0.20

    # category match
    if category and str(row["subcategory"]).lower() == category.lower():
        score += 2.0

    # platform match
    if platforms:
        if str(row["platform"]).strip().lower() in [p.lower() for p in platforms]:
            score += 1.5

    # budget match
    price = float(row["price_discounted"])
    if budget_high is not None:
        if budget_low is not None and budget_low <= price <= budget_high:
            score += 1.5
        elif budget_low == 0.0 and price <= budget_high:
            score += 1.5

    # concern match
    row_concerns = str(row["target_concerns"]).lower()
    for concern in concerns:
        if concern.lower() in row_concerns:
            score += 1.2

    # skin type match
    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            score += 1.0

    return score


def overall_score(row):
    return row["rating_avg"] * 0.7 + row["avg_sentiment_score"] * 5 * 0.3


def build_explanation(row, category, skin_types, concerns, budget_high, platforms):
    reasons = []

    reasons.append(f"high rating of {row['rating_avg']}")
    reasons.append(f"positive sentiment score of {row['avg_sentiment_score']:.2f}")

    if category and str(row["subcategory"]).lower() == category.lower():
        reasons.append(f"matches your requested category ({category})")

    if platforms and str(row["platform"]).lower() in [p.lower() for p in platforms]:
        reasons.append(f"available on your requested platform ({row['platform']})")

    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            reasons.append(f"suitable for {skin.lower()} skin")

    row_concerns = str(row["target_concerns"]).lower()
    for concern in concerns:
        if concern.lower() in row_concerns:
            reasons.append(f"targets {concern.lower()}")

    if budget_high is not None and float(row["price_discounted"]) <= budget_high:
        reasons.append(f"fits your budget")

    return ", ".join(reasons)


def chatbot_response(best_for_need, best_overall):
    text = []
    text.append("Here is your recommendation summary:\n")

    text.append("1. Best product for your need:")
    text.append(f"- {best_for_need['product_name']} by {best_for_need['brand']}")
    text.append(f"- Platform: {best_for_need['platform']}")
    text.append(f"- Category: {best_for_need['subcategory']}")
    text.append(f"- Price: ${best_for_need['price_discounted']}")
    text.append(f"- Rating: {best_for_need['rating_avg']}")
    text.append("")

    text.append("2. Best overall product:")
    text.append(f"- {best_overall['product_name']} by {best_overall['brand']}")
    text.append(f"- Platform: {best_overall['platform']}")
    text.append(f"- Category: {best_overall['subcategory']}")
    text.append(f"- Price: ${best_overall['price_discounted']}")
    text.append(f"- Rating: {best_overall['rating_avg']}")

    return "\n".join(text)


def main():
    products_file = Path("data/raw/yesstyle_products.csv")
    sentiment_file = Path("data/processed/yesstyle_sentiment.csv")
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

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
    skin_types = extract_skin_types(user_query)
    concerns = extract_concerns(user_query)
    platforms = extract_platforms(user_query)

    filtered = df.copy()

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
        print("\nNo matching products found after filtering.")
        return

    filtered = filtered.copy()

    filtered["best_for_need_score"] = filtered.apply(
        lambda row: score_product(
            row, budget_low, budget_high, category, skin_types, concerns, platforms
        ),
        axis=1
    )

    filtered["best_overall_score"] = filtered.apply(overall_score, axis=1)

    filtered = filtered.sort_values(by="best_for_need_score", ascending=False)

    best_for_need = filtered.iloc[0]
    best_overall = filtered.sort_values(by="best_overall_score", ascending=False).iloc[0]
    top_3 = filtered.head(3).copy()

    top_3["explanation"] = top_3.apply(
        lambda row: build_explanation(
            row, category, skin_types, concerns, budget_high, platforms
        ),
        axis=1
    )

    export_cols = [
        "product_id",
        "platform",
        "brand",
        "product_name",
        "subcategory",
        "price_discounted",
        "rating_avg",
        "skin_type",
        "target_concerns",
        "avg_sentiment_score",
        "best_for_need_score",
        "best_overall_score",
        "explanation"
    ]

    top_3[export_cols].to_csv(
        output_dir / "top_recommendations.csv",
        index=False
    )

    print("\n" + "=" * 75)
    print("SMART RECOMMENDER V3")
    print("=" * 75)

    print("\nYour Query:")
    print(user_query)

    print("\nDetected Preferences:")
    print(f"Category   : {category if category else 'Not detected'}")
    print(f"Skin Type  : {', '.join(skin_types) if skin_types else 'Not detected'}")
    print(f"Concerns   : {', '.join(concerns) if concerns else 'Not detected'}")
    print(f"Platform   : {', '.join(platforms) if platforms else 'Not detected'}")

    if budget_high is not None:
        if budget_low is not None and budget_low > 0:
            print(f"Budget     : ${budget_low:.0f} to ${budget_high:.0f}")
        else:
            print(f"Budget     : Under ${budget_high:.0f}")
    else:
        print("Budget     : Not detected")

    print("\n" + "-" * 75)
    print("BEST PRODUCT FOR YOUR NEED")
    print("-" * 75)
    print(f"Product Name   : {best_for_need['product_name']}")
    print(f"Brand          : {best_for_need['brand']}")
    print(f"Platform       : {best_for_need['platform']}")
    print(f"Category       : {best_for_need['subcategory']}")
    print(f"Price          : ${best_for_need['price_discounted']}")
    print(f"Rating         : {best_for_need['rating_avg']}")
    print(f"Skin Type      : {best_for_need['skin_type']}")
    print(f"Concerns       : {best_for_need['target_concerns']}")
    print(f"Sentiment Score: {best_for_need['avg_sentiment_score']:.2f}")
    print(f"Match Score    : {best_for_need['best_for_need_score']:.2f}")
    print("Why Recommended:")
    print(build_explanation(best_for_need, category, skin_types, concerns, budget_high, platforms))

    print("\n" + "-" * 75)
    print("BEST OVERALL PRODUCT")
    print("-" * 75)
    print(f"Product Name   : {best_overall['product_name']}")
    print(f"Brand          : {best_overall['brand']}")
    print(f"Platform       : {best_overall['platform']}")
    print(f"Category       : {best_overall['subcategory']}")
    print(f"Price          : ${best_overall['price_discounted']}")
    print(f"Rating         : {best_overall['rating_avg']}")
    print(f"Overall Score  : {best_overall['best_overall_score']:.2f}")

    print("\n" + "-" * 75)
    print("TOP 3 MATCHING PRODUCTS")
    print("-" * 75)
    print(
        top_3[[
            "product_name",
            "brand",
            "platform",
            "subcategory",
            "price_discounted",
            "rating_avg",
            "skin_type",
            "target_concerns",
            "avg_sentiment_score",
            "best_for_need_score"
        ]].to_string(index=False)
    )

    print("\n" + "-" * 75)
    print("CHATBOT STYLE RESPONSE")
    print("-" * 75)
    print(chatbot_response(best_for_need, best_overall))

    print("\nRecommendations exported to: outputs/top_recommendations.csv")


if __name__ == "__main__":
    main()
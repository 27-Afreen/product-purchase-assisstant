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

    # Quality-aware base score
    score += float(row["quality_score"]) * 0.5

    # Category match
    if category and str(row["subcategory"]).lower() == category.lower():
        score += 2.0

    # Platform match
    if platforms and str(row["platform"]).lower() in [p.lower() for p in platforms]:
        score += 1.5

    # Budget match
    price = float(row["price_discounted"])
    if budget_high is not None:
        if budget_low is not None and budget_low <= price <= budget_high:
            score += 1.5
        elif budget_low == 0.0 and price <= budget_high:
            score += 1.5

    # Skin type match
    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            score += 1.0

    # Need / concern / use-case match
    row_needs = str(row["target_concerns_or_use_cases"]).lower()
    for need in needs:
        if need.lower() in row_needs:
            score += 1.2

    return round(score, 4)


def compute_best_overall_score(row):
    return round((float(row["quality_score"]) * 0.8) + (float(row["rating_avg"]) * 0.2), 4)


def build_explanation(row, category, platforms, skin_types, needs, budget_high):
    reasons = []

    reasons.append(f"high quality score ({row['quality_score']:.2f})")
    reasons.append(f"strong rating ({row['rating_avg']})")
    sentiment_value = float(row["avg_sentiment_score"])

    if sentiment_value > 0.1:
        reasons.append(f"positive review sentiment ({sentiment_value:.2f})")
    elif sentiment_value < -0.1:
        reasons.append(f"negative review sentiment ({sentiment_value:.2f})")
    else:
        reasons.append(f"neutral review sentiment ({sentiment_value:.2f})")
    if float(row["review_count"]) > 500:
        reasons.append(f"supported by many reviews ({int(row['review_count'])})")

    if category and str(row["subcategory"]).lower() == category.lower():
        reasons.append(f"matches your requested category ({category})")

    if platforms and str(row["platform"]).lower() in [p.lower() for p in platforms]:
        reasons.append(f"available on your requested platform ({row['platform']})")

    row_skin = str(row["skin_type"]).lower()
    for skin in skin_types:
        if skin.lower() in row_skin:
            reasons.append(f"suits {skin.lower()} skin")

    row_needs = str(row["target_concerns_or_use_cases"]).lower()
    for need in needs:
        if need.lower() in row_needs:
            reasons.append(f"targets {need.lower()}")

    if budget_high is not None and float(row["price_discounted"]) <= budget_high:
        reasons.append(f"fits your budget")

    return ", ".join(reasons)


def main():
    products_file = Path("data/raw/products_master.csv")
    sentiment_file = Path("data/processed/sentiment_master.csv")
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not products_file.exists():
        print("Missing file: data/raw/products_master.csv")
        return

    if not sentiment_file.exists():
        print("Missing file: data/processed/sentiment_master.csv")
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

    # New quality score
    df["quality_score"] = df.apply(compute_quality_score, axis=1)

    user_query = input("Enter your product query: ").strip()

    domain = extract_domain(user_query)
    category = extract_category(user_query)
    platforms = extract_platforms(user_query)
    skin_types = extract_skin_types(user_query)
    needs = extract_needs(user_query)
    budget_low, budget_high = extract_budget(user_query)

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
        print("\nNo matching products found.")
        return

    filtered = filtered.copy()

    filtered["match_score"] = filtered.apply(
        lambda row: score_product(
            row, category, platforms, skin_types, needs, budget_low, budget_high
        ),
        axis=1
    )

    filtered["best_overall_score"] = filtered.apply(compute_best_overall_score, axis=1)

    filtered = filtered.sort_values(by="match_score", ascending=False)

    best_for_need = filtered.iloc[0]
    best_overall = filtered.sort_values(by="best_overall_score", ascending=False).iloc[0]
    top_3 = filtered.head(3).copy()

    top_3["explanation"] = top_3.apply(
        lambda row: build_explanation(
            row, category, platforms, skin_types, needs, budget_high
        ),
        axis=1
    )

    export_cols = [
        "product_id",
        "platform",
        "domain",
        "subcategory",
        "brand",
        "product_name",
        "price_discounted",
        "rating_avg",
        "review_count",
        "avg_sentiment_score",
        "quality_score",
        "match_score",
        "best_overall_score",
        "target_concerns_or_use_cases",
        "explanation"
    ]

    top_3[export_cols].to_csv(
        output_dir / "top_recommendations_multidomain.csv",
        index=False
    )

    print("\n" + "=" * 75)
    print("QUALITY-AWARE MULTIDOMAIN PRODUCT RECOMMENDER")
    print("=" * 75)

    print(f"\nYour Query          : {user_query}")
    print(f"Detected Domain     : {domain if domain else 'Not detected'}")
    print(f"Detected Category   : {category if category else 'Not detected'}")
    print(f"Detected Platform   : {', '.join(platforms) if platforms else 'Not detected'}")
    print(f"Detected Skin Type  : {', '.join(skin_types) if skin_types else 'Not detected'}")
    print(f"Detected Needs      : {', '.join(needs) if needs else 'Not detected'}")

    if budget_high is not None:
        if budget_low is not None and budget_low > 0:
            print(f"Detected Budget     : ${budget_low:.0f} to ${budget_high:.0f}")
        else:
            print(f"Detected Budget     : Under ${budget_high:.0f}")
    else:
        print("Detected Budget     : Not detected")

    print("\n" + "-" * 75)
    print("BEST PRODUCT FOR YOUR NEED")
    print("-" * 75)
    print(f"Product Name        : {best_for_need['product_name']}")
    print(f"Brand               : {best_for_need['brand']}")
    print(f"Platform            : {best_for_need['platform']}")
    print(f"Domain              : {best_for_need['domain']}")
    print(f"Category            : {best_for_need['subcategory']}")
    print(f"Price               : ${best_for_need['price_discounted']}")
    print(f"Rating              : {best_for_need['rating_avg']}")
    print(f"Review Count        : {best_for_need['review_count']}")
    print(f"Sentiment Score     : {best_for_need['avg_sentiment_score']:.2f}")
    print(f"Quality Score       : {best_for_need['quality_score']:.2f}")
    print(f"Match Score         : {best_for_need['match_score']:.2f}")
    print(f"Use Cases / Concerns: {best_for_need['target_concerns_or_use_cases']}")
    print("Why Recommended     :")
    print(build_explanation(best_for_need, category, platforms, skin_types, needs, budget_high))

    print("\n" + "-" * 75)
    print("BEST OVERALL PRODUCT")
    print("-" * 75)
    print(f"Product Name        : {best_overall['product_name']}")
    print(f"Brand               : {best_overall['brand']}")
    print(f"Platform            : {best_overall['platform']}")
    print(f"Domain              : {best_overall['domain']}")
    print(f"Category            : {best_overall['subcategory']}")
    print(f"Price               : ${best_overall['price_discounted']}")
    print(f"Rating              : {best_overall['rating_avg']}")
    print(f"Review Count        : {best_overall['review_count']}")
    print(f"Sentiment Score     : {best_overall['avg_sentiment_score']:.2f}")
    print(f"Quality Score       : {best_overall['quality_score']:.2f}")
    print(f"Overall Score       : {best_overall['best_overall_score']:.2f}")

    print("\n" + "-" * 75)
    print("TOP 3 MATCHING PRODUCTS")
    print("-" * 75)
    print(
        top_3[[
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
        ]].to_string(index=False)
    )

    print("\nRecommendations exported to: outputs/top_recommendations_multidomain.csv")


if __name__ == "__main__":
    main()
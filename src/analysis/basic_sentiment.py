import pandas as pd
from pathlib import Path
from textblob import TextBlob

def get_sentiment(text):
    polarity = TextBlob(str(text)).sentiment.polarity

    if polarity > 0.1:
        label = "positive"
    elif polarity < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return label, polarity

def main():
    clean_file = Path("data/processed/yesstyle_reviews_clean.csv")
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(clean_file)

    sentiment_results = df["clean_text"].apply(get_sentiment)
    df["sentiment_label"] = sentiment_results.apply(lambda x: x[0])
    df["sentiment_score"] = sentiment_results.apply(lambda x: x[1])

    df[[
        "review_id",
        "product_id",
        "clean_text",
        "tokens",
        "text_length",
        "sentiment_label",
        "sentiment_score"
    ]].to_csv(output_dir / "yesstyle_sentiment.csv", index=False)

    print("Basic sentiment file created successfully.")

if __name__ == "__main__":
    main()
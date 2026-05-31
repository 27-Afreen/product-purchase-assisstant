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
    input_file = Path("data/processed/reviews_clean_master.csv")
    output_file = Path("data/processed/sentiment_master.csv")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_file)

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
    ]].to_csv(output_file, index=False)

    print("Master sentiment file created successfully.")

if __name__ == "__main__":
    main()
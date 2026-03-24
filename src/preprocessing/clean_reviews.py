import pandas as pd
import re
from pathlib import Path

def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def main():
    input_file = Path("data/raw/yesstyle_reviews.csv")
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_file)
    df["clean_text"] = df["review_text"].apply(clean_text)
    df["tokens"] = df["clean_text"].apply(lambda x: " ".join(x.split()))
    df["text_length"] = df["clean_text"].apply(lambda x: len(x.split()))

    df[["review_id", "product_id", "clean_text", "tokens", "text_length"]].to_csv(
        output_dir / "yesstyle_reviews_clean.csv",
        index=False
    )

    print("Cleaned reviews saved successfully.")

if __name__ == "__main__":
    main()
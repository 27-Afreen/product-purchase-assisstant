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
    input_file = Path("data/raw/reviews_master.csv")
    output_file = Path("data/processed/reviews_clean_master.csv")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_file)
    df["clean_text"] = df["review_text"].apply(clean_text)
    df["tokens"] = df["clean_text"].apply(lambda x: " ".join(x.split()))
    df["text_length"] = df["clean_text"].apply(lambda x: len(x.split()))

    df[["review_id", "product_id", "clean_text", "tokens", "text_length"]].to_csv(
        output_file, index=False
    )

    print("Master cleaned reviews file created successfully.")

if __name__ == "__main__":
    main()
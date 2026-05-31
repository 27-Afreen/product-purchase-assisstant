"""
Sentiment analyzer using a fine-tuned DistilBERT model.
Returns a POSITIVE confidence score (0.0 – 1.0) for any text.
Used to boost ranking of products whose review blurbs score more positively.
"""

import os

# Lazy-loaded globals so the model is only loaded once per process
_tokenizer = None
_model = None
_device = None

MODEL_DIR = os.path.join(os.path.dirname(__file__), "sentiment_model")


def _load():
    """Load tokenizer and model on first use."""
    global _tokenizer, _model, _device

    if _model is not None:
        return True

    try:
        import torch
        from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

        _device = torch.device("cpu")  # CPU-only; fast enough for 4 short texts

        _tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
        _model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
        _model.to(_device)
        _model.eval()

        print("DistilBERT sentiment model loaded.")
        return True

    except ImportError:
        print("torch/transformers not installed - sentiment scoring disabled.")
        return False
    except Exception as e:
        print(f"Could not load sentiment model: {e}")
        return False


def score(text: str) -> float:
    """
    Return POSITIVE confidence score in [0.0, 1.0].
    Returns 0.5 (neutral) if the model is unavailable.
    """
    if not text or not text.strip():
        return 0.5

    if not _load():
        return 0.5

    try:
        import torch

        inputs = _tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=True,
        )
        inputs = {k: v.to(_device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = _model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)

        # id2label: 0 = NEGATIVE, 1 = POSITIVE
        positive_prob = probs[0][1].item()
        return round(positive_prob, 4)

    except Exception as e:
        print(f"Sentiment inference error: {e}")
        return 0.5


def score_batch(texts: list) -> list:
    """Score multiple texts at once. Returns list of floats."""
    if not texts:
        return []

    if not _load():
        return [0.5] * len(texts)

    try:
        import torch

        inputs = _tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=True,
        )
        inputs = {k: v.to(_device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = _model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)

        return [round(probs[i][1].item(), 4) for i in range(len(texts))]

    except Exception as e:
        print(f"Sentiment batch inference error: {e}")
        return [0.5] * len(texts)

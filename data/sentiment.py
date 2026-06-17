# data/sentiment.py
"""
News-sentiment fundamental feature via FinBERT (financial BERT).

Pipeline (all free, no paid keys):
  1. pull headlines from GDELT (api.gdeltproject.org — free, no key) for the instrument
  2. score each headline with FinBERT (ProsusAI/finbert) -> P(pos) - P(neg) in [-1, 1]
  3. aggregate to a DAILY sentiment series, leakage-shift to next day, save to
     data/raw/SENTIMENT.parquet as column f_news_sentiment

The meta-labeler (strategy/meta_label.py) auto-loads f_news_sentiment if present, so the
AI model gains a fundamental/news feature with no code change.

GRACEFUL DEGRADATION: if transformers/torch or the network is unavailable, it writes
nothing (the model simply runs without this feature) and prints how to enable it.

Run (needs network + `pip install transformers torch`):
  python data/sentiment.py --query "gold XAUUSD OR Federal Reserve OR inflation" --days 365
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
OUT = RAW / "SENTIMENT.parquet"
FINBERT = "ProsusAI/finbert"


def _load_finbert():
    """Lazy import; returns a scoring fn or None if unavailable."""
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
    except Exception as e:
        print(f"  ! transformers/torch not available ({e}). pip install transformers torch")
        return None
    tok = AutoTokenizer.from_pretrained(FINBERT)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT)
    model.eval()
    labels = model.config.id2label  # {0:'positive',1:'negative',2:'neutral'} for finbert

    def score(texts):
        import torch
        if not texts:
            return []
        out = []
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            enc = tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=64)
            with torch.no_grad():
                probs = torch.softmax(model(**enc).logits, dim=-1).numpy()
            for p in probs:
                d = {labels[j].lower(): p[j] for j in range(len(p))}
                out.append(float(d.get("positive", 0) - d.get("negative", 0)))   # [-1,1]
        return out
    return score


def pull_gdelt(query, days):
    """Free GDELT article list (no key). Returns DataFrame[date, title]."""
    import requests
    url = ("https://api.gdeltproject.org/api/v2/doc/doc"
           f"?query={requests.utils.quote(query)}&mode=artlist&format=json"
           f"&maxrecords=250&timespan={int(days)}d&sort=datedesc")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    arts = r.json().get("articles", [])
    rows = [{"date": pd.to_datetime(a["seendate"]).normalize(), "title": a.get("title", "")}
            for a in arts if a.get("seendate")]
    return pd.DataFrame(rows)


def build(query, days):
    score = _load_finbert()
    if score is None:
        print("  -> sentiment feature skipped (model unavailable); pipeline still runs without it.")
        return
    try:
        news = pull_gdelt(query, days)
    except Exception as e:
        print(f"  ! GDELT pull failed (network?): {e}")
        return
    if news.empty:
        print("  ! no headlines returned")
        return
    news["s"] = score(news["title"].tolist())
    daily = news.groupby("date")["s"].mean().rename("f_news_sentiment").to_frame()
    daily = daily.shift(1).dropna()      # leakage guard: yesterday's news available today
    daily.index.name = "time"
    # merge into existing SENTIMENT/FUNDAMENTALS if present
    daily.to_parquet(OUT)
    print(f"  saved {OUT}  ({len(daily)} days, mean sentiment={daily['f_news_sentiment'].mean():+.3f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="gold price OR Federal Reserve OR inflation OR XAUUSD")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()
    print("=== FinBERT news sentiment ===")
    build(args.query, args.days)


if __name__ == "__main__":
    main()

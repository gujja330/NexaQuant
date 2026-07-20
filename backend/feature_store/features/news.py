"""News features from CanonicalNews rows."""
from __future__ import annotations

from datetime import date

from backend.canonical.schemas import CanonicalDataset


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    news = canon.get("news")
    if not news or not news.rows:
        return out

    # Latest row per symbol
    latest: dict[str, object] = {}
    for n in sorted(news.rows, key=lambda r: r.asof):
        latest[n.symbol] = n

    for sym in universe:
        n = latest.get(sym)
        if n is None:
            out[sym] = {}
            continue
        pol = None
        if n.n_headlines > 0:
            pol = round((n.n_positive - n.n_negative) / n.n_headlines, 4)
        out[sym] = {
            "news_sentiment":     n.sentiment,
            "news_n_headlines":   int(n.n_headlines),
            "news_n_positive":    int(n.n_positive),
            "news_n_negative":    int(n.n_negative),
            "news_polarity_ratio": pol,
        }
    return out

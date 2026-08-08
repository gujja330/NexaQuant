"""News/Event sub-engine · 5% weight of Investability Score.

Wave 1.5: consumes existing reports/context/sector_news.json + ai_market_narrative.json.
Ticker-level news impact classifier:
    · Very Negative   → -30 points
    · Negative        → -15 points
    · Neutral         → 0 (baseline 50)
    · Positive        → +15 points
    · Very Positive   → +30 points

Wave 2 (Sprint K): dedicated ticker-level news impact feed · earnings news
· corporate actions · management commentary sentiment.
"""
from __future__ import annotations

import json
from pathlib import Path


def _load_news(root: Path, market: str) -> list:
    """Consolidate news items from all available news sources."""
    items = []
    for name in ["context/sector_news", "ai_market_narrative", "ai_news_narrative"]:
        p = root / "reports" / f"{name}.json"
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            # Various shapes · try common ones
            for key in ("items", "news", "articles", "narratives", "headlines"):
                if key in d and isinstance(d[key], list):
                    items.extend(d[key])
        except Exception:
            continue
    return items


def _classify_impact(text: str) -> int:
    """Rule-based impact classifier · returns -30 to +30."""
    if not text: return 0
    text = text.lower()

    very_negative_keywords = [
        "bankruptcy", "fraud", "sebi action", "delisting", "auditor resigned",
        "going concern", "restated", "class action", "criminal", "raid",
        "arrest", "collapse", "insolvency",
    ]
    negative_keywords = [
        "downgrade", "miss", "cut guidance", "loss", "weak", "concern",
        "investigation", "sued", "warning", "risk", "declined", "fall",
        "underperform", "reduce", "sell", "avoid",
    ]
    positive_keywords = [
        "upgrade", "beat", "raised guidance", "strong", "outperform",
        "win", "growth", "expansion", "record", "surge",
        "buy", "accumulate", "target raised", "positive",
    ]
    very_positive_keywords = [
        "acquisition", "merger", "breakthrough", "landmark", "biggest ever",
        "multibagger", "structural growth", "transformational",
    ]

    if any(k in text for k in very_negative_keywords):
        return -30
    if any(k in text for k in negative_keywords):
        return -15
    if any(k in text for k in very_positive_keywords):
        return +30
    if any(k in text for k in positive_keywords):
        return +15
    return 0


def score(ticker: str, market: str, root: Path) -> tuple[float, dict]:
    short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    signals = {"ticker_mentions": [], "sector_backdrop_impact": 0}

    news_items = _load_news(root, market)

    # Ticker-specific mentions
    ticker_impact = 0
    n_ticker_hits = 0
    for item in news_items:
        text = ""
        if isinstance(item, dict):
            text = " ".join(str(item.get(k, "")) for k in ("title", "headline", "text", "summary", "narrative"))
        elif isinstance(item, str):
            text = item
        if not text: continue
        text_up = text.upper()
        if short in text_up:
            impact = _classify_impact(text)
            if impact != 0:
                signals["ticker_mentions"].append({"text": text[:120], "impact": impact})
                ticker_impact += impact
                n_ticker_hits += 1

    # Base score · 50 neutral · adjust by impact
    if n_ticker_hits > 0:
        avg_impact = ticker_impact / n_ticker_hits
        score_0_100 = max(0, min(100, 50 + avg_impact))
    else:
        # No ticker-specific news · use sector/market backdrop as proxy
        market_impact = 0
        n_market = 0
        for item in news_items[:10]:  # top 10 most recent
            text = ""
            if isinstance(item, dict):
                text = " ".join(str(item.get(k, "")) for k in ("title", "headline", "text", "summary", "narrative"))
            elif isinstance(item, str):
                text = item
            if text:
                impact = _classify_impact(text)
                market_impact += impact
                n_market += 1
        if n_market:
            avg = market_impact / n_market
            signals["sector_backdrop_impact"] = avg
            score_0_100 = max(0, min(100, 50 + avg * 0.5))  # dampened · sector proxy
        else:
            score_0_100 = 50.0  # true neutral · no news data

    return round(score_0_100, 1), {
        "engine":     "news.v1",
        "score":      round(score_0_100, 1),
        "n_ticker_mentions": n_ticker_hits,
        "n_total_news":     len(news_items),
        "signals":    signals,
    }

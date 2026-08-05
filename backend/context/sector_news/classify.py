"""Sector news classifier · sentiment from cross-sector return divergence.

Output: reports/ai_news_narrative.json (fills the previously-missing file)
+ reports/context/sector_news.json (structured per-sector sentiment)

Method (Phase 2A proxy · replace with real NLP in Phase 2B):
    · Compute today's average return per sector from bar data
    · Compute market average return (all sectors weighted equally)
    · Sector sentiment = (sector_avg_return - market_avg_return) × amplifier
    · Cap at ±1.0 · then scale to ±1 range for NewsAdapter

Divergent negative sectors surface as "negative sector news" · captures
the operator's IT-down case (IT drops 2% while market flat = -0.8 sentiment).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _bars_dir(root: Path, market: str) -> Path:
    if market == "usa":
        return root / "usa" / "data" / "raw" / "us"
    return root / "data" / "raw" / "india"


def _sector_map(root: Path, market: str) -> dict:
    if market == "india":
        try:
            import sys as _sys
            _sys.path.insert(0, str(root))
            from india.sectors import SECTORS as _S
            return {k.upper(): v for k, v in _S.items()}
        except Exception:
            pass
    return {}


def compute_sector_news(root: Path, market: str, asof: str) -> dict:
    try:
        import pandas as pd
    except ImportError:
        return {"available": False, "reason": "pandas missing"}

    bars = _bars_dir(root, market)
    if not bars.exists():
        return {"available": False, "reason": f"no bars at {bars}"}

    sector_map = _sector_map(root, market)
    sector_returns: dict[str, list[float]] = {}

    for pq in bars.glob("*_D1.parquet"):
        if pq.name.startswith("_IDX_"): continue
        ticker = pq.stem.replace("_D1", "").replace(".NS", "").replace(".BO", "")
        sector = sector_map.get(ticker.upper(), "Unknown")
        try:
            df = pd.read_parquet(pq)
            col = "Close" if "Close" in df.columns else "close" if "close" in df.columns else None
            if col is None or len(df) < 2: continue
            last = float(df[col].iloc[-1])
            prev = float(df[col].iloc[-2])
            if prev == 0: continue
            ret = (last - prev) / prev
            sector_returns.setdefault(sector, []).append(ret)
        except Exception:
            continue

    if not sector_returns:
        return {"available": False, "reason": "no returns computed"}

    # Sector averages
    sector_avg = {s: sum(v) / len(v) for s, v in sector_returns.items() if v}
    # Market avg = mean of sector averages (equal weight per sector)
    market_avg = sum(sector_avg.values()) / len(sector_avg) if sector_avg else 0
    # Sentiment = divergence · amplified so ±2% relative diff → ±1.0
    sector_sentiment = {}
    for s, avg in sector_avg.items():
        diff = avg - market_avg
        sent = max(-1.0, min(1.0, diff * 50))    # ±2% diff → ±1
        sector_sentiment[s] = round(sent, 3)

    # Identify most negative sectors (news-worthy)
    negative_sectors = sorted(
        [(s, v) for s, v in sector_sentiment.items() if v < -0.3],
        key=lambda x: x[1])
    positive_sectors = sorted(
        [(s, v) for s, v in sector_sentiment.items() if v > 0.3],
        key=lambda x: -x[1])

    return {
        "engine":            "aegis.context.sector_news.v0.1_divergence",
        "asof":              asof, "market": market,
        "generated_utc":     datetime.now(timezone.utc).isoformat(),
        "available":         True,
        "method":            "cross-sector return divergence proxy",
        "market_avg_return": round(market_avg, 4),
        "sector_sentiment":  sector_sentiment,
        "n_sectors":         len(sector_sentiment),
        "top_negative": [{"sector": s, "sentiment": v} for s, v in negative_sectors[:5]],
        "top_positive": [{"sector": s, "sentiment": v} for s, v in positive_sectors[:5]],
        "note": "Phase 2A · derived from bar divergence · Phase 2B replaces with real NLP",
    }


def emit(root: Path, payload: dict) -> Path:
    # Primary output that NewsAdapter reads
    p = root / "reports" / "context" / "sector_news.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    # Also fill the previously-missing file for backward compatibility
    p2 = root / "reports" / "ai_news_narrative.json"
    payload2 = {
        **payload,
        "engine":  "aegis.ai_news_narrative.v1_divergence_proxy",
        "sector_sentiment": payload["sector_sentiment"],
    }
    p2.write_text(json.dumps(payload2, indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p

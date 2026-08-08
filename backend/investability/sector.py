"""Sector sub-engine · 10% weight of Investability Score.

Wave 1.5: consumes existing reports/sector_rotation.json + sector_context.json

Signals:
    Sector momentum rank    · top quartile = healthy
    Sector relative perf    · sector vs benchmark (positive = strength)
    Sector breadth          · % of sector members above 50-DMA
    Sector rotation phase   · early/mid/late-cycle
    Ticker sector known     · has any sector classification at all
"""
from __future__ import annotations

import json
from pathlib import Path


def _load_sector_data(root: Path, market: str) -> dict:
    """Load consolidated sector data from existing engine outputs."""
    reports = root / "reports"
    data = {}
    for name in ["sector_rotation", "sector_report", "sector_context"]:
        p = reports / f"{name}.json"
        if p.exists():
            try:
                data[name] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return data


def _find_ticker_sector(ticker: str, sector_cache_path: Path) -> str:
    """Look up ticker's sector from the cache we already built."""
    if not sector_cache_path.exists(): return ""
    try:
        cache = json.loads(sector_cache_path.read_text(encoding="utf-8"))
        short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
        for market_bucket in cache.values():
            if isinstance(market_bucket, dict) and short in market_bucket:
                return market_bucket[short] or ""
    except Exception:
        pass
    return ""


def score(ticker: str, market: str, root: Path) -> tuple[float, dict]:
    signals = {}
    hits = 0
    total = 0

    def check(name, ok, weight=1.0, extra=None):
        nonlocal hits, total
        total += weight
        signals[name] = {"ok": bool(ok), "weight": weight, "extra": extra}
        if ok: hits += weight

    # Ticker's sector · from cache (if present, it's classified)
    sector_name = _find_ticker_sector(ticker,
                                                       root / "reports" / "sector_cache.json")
    check("sector_classified", bool(sector_name), weight=0.5,
              extra={"sector": sector_name})

    sector_data = _load_sector_data(root, market)

    # Sector rotation phase (if available)
    rot = sector_data.get("sector_rotation", {})
    sector_rank = None

    # sector_rotation.json structure varies · try common shapes
    if sector_name and rot:
        # Try to find this sector in the rotation data
        top_sectors = rot.get("top_sectors") or rot.get("leaders") or []
        bottom_sectors = rot.get("bottom_sectors") or rot.get("laggards") or []
        if isinstance(top_sectors, list):
            sector_rank = "top" if sector_name in [str(s) for s in top_sectors] \
                                else "bottom" if sector_name in [str(s) for s in bottom_sectors] \
                                else "middle"
        check("sector_not_bottom_quartile", sector_rank != "bottom", weight=2.0,
                  extra={"sector_rank": sector_rank})
        check("sector_top_quartile", sector_rank == "top", weight=1.5,
                  extra={"sector_rank": sector_rank})

    # Sector momentum score from sector_report
    rpt = sector_data.get("sector_report", {})
    if sector_name and rpt:
        sectors = rpt.get("sectors") or []
        for s in (sectors if isinstance(sectors, list) else []):
            if isinstance(s, dict) and s.get("name") == sector_name:
                mom = s.get("momentum") or s.get("momentum_score")
                if mom is not None:
                    check("sector_momentum_positive", mom > 0, weight=1.5,
                              extra={"momentum": mom})
                break

    # Neutral baseline · if no sector data at all, don't penalize
    if total < 1.0:
        return 50.0, {"engine": "sector.v1", "score": 50.0,
                              "signals": signals, "note": "insufficient sector data · neutral"}

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "sector.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
        "sector":     sector_name,
    }

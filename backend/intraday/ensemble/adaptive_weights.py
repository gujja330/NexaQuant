"""Adaptive weights · per-signal ensemble blender.

Independent from delivery's adaptive weights · own learning corpus at
reports/intraday/learning.parquet. Configurable via
configs/intraday_ensemble_weights.json (investor-editable).
"""
from __future__ import annotations

import json
from pathlib import Path


DEFAULT_WEIGHTS = {
    # SMC gets top weight · institutional-grade confluence-based signal
    "smart_money":            0.35,
    "orb":                    0.15,
    "vwap_pullback":          0.10,
    "bollinger_reversion":    0.10,
    "ema_crossover":          0.10,
    "gap_and_go":             0.10,
    "sector_momentum":        0.05,
    "news_impact":            0.05,
}


def default_weights(root: Path | None = None) -> dict:
    """Load investor-configured weights · fall back to DEFAULT_WEIGHTS."""
    if root is None:
        return dict(DEFAULT_WEIGHTS)
    cfg = root / "configs" / "intraday_ensemble_weights.json"
    if not cfg.exists():
        return dict(DEFAULT_WEIGHTS)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return data.get("weights") or dict(DEFAULT_WEIGHTS)
    except Exception:
        return dict(DEFAULT_WEIGHTS)


def blend_signals(signals: list, weights: dict | None = None) -> dict:
    """Blend a list of SignalScore into per-ticker aggregate scores.

    Returns: {ticker: {"direction": LONG|SHORT|SKIP, "blended_score": float,
                        "contributions": {signal_id: weighted_contribution}}}
    """
    w = weights or DEFAULT_WEIGHTS
    per_ticker: dict[str, dict] = {}
    for s in signals:
        if s is None:
            continue
        t = s.ticker
        rec = per_ticker.setdefault(t, {"blended_score": 0.0, "contributions": {}})
        contrib = s.score * w.get(s.signal_id, 0)
        rec["blended_score"] += contrib
        rec["contributions"][s.signal_id] = contrib
    # Raised activation threshold from 0.10 → 0.30 · quality > quantity
    for t, rec in per_ticker.items():
        rec["direction"] = ("LONG" if rec["blended_score"] > 0.30 else
                              "SHORT" if rec["blended_score"] < -0.30 else "SKIP")
    return per_ticker

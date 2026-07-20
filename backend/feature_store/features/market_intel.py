"""Market Intelligence features — joined from market_intelligence.json.

These are MARKET-LEVEL — same values broadcast to every ticker in the universe.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.canonical.schemas import CanonicalDataset


def _load_market_intel(repo_root: Path, market_name: str) -> dict | None:
    if market_name == "usa":
        p = repo_root / "usa" / "reports" / "market_intelligence.json"
    else:
        p = repo_root / "reports" / "market_intelligence.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str,
             repo_root: Path | None = None) -> dict[str, dict]:
    if repo_root is None:
        return {t: {} for t in universe}
    mi = _load_market_intel(Path(repo_root), market_name)
    if not mi:
        return {t: {} for t in universe}

    sigs = mi.get("signals", {})
    def _v(key: str) -> object:
        s = sigs.get(key)
        if isinstance(s, dict):
            return s.get("value")
        return None

    row = {
        "mi_regime":                   mi.get("regime"),
        "mi_composite_score":          mi.get("composite_score"),
        "mi_breadth_above_20ma_pct":   _v("breadth_above_20ma"),
        "mi_breadth_at_52w_high_pct":  _v("breadth_at_52w_high"),
        "mi_liquidity_5v20_pct":       _v("liquidity_5v20"),
        "mi_news_pulse":               _v("news_pulse"),
        "mi_benchmark_1m_pct":         _v("benchmark_1m_pct"),
    }
    return {t: dict(row) for t in universe}

"""Diversification metrics — HHI, effective N, top-K, sector spread."""
from __future__ import annotations

from backend.portfolio.types import Position


def compute_diversification_metrics(positions: list[Position]) -> dict:
    """Return diversification metrics for a portfolio.

    Returns:
      {
        "hhi":              float,      # 0..1
        "effective_n":      float,      # 1/HHI (∞ if no positions)
        "top_5_pct":        float,      # fraction of gross in top-5
        "per_sector_pct":   dict,       # sector -> exposure
        "n_sectors":        int,
        "n_long":           int,
        "n_short":          int,
      }
    """
    if not positions:
        return {"hhi": 0.0, "effective_n": 0.0, "top_5_pct": 0.0,
                 "per_sector_pct": {}, "n_sectors": 0, "n_long": 0, "n_short": 0}

    gross = sum(abs(p.weight) for p in positions)
    if gross <= 0:
        return {"hhi": 0.0, "effective_n": 0.0, "top_5_pct": 0.0,
                 "per_sector_pct": {}, "n_sectors": 0, "n_long": 0, "n_short": 0}

    # HHI on absolute (gross-normalised) weights
    normed = [abs(p.weight) / gross for p in positions]
    hhi = sum(w * w for w in normed)
    effective_n = (1.0 / hhi) if hhi > 0 else 0.0

    # Top-5 concentration
    abs_sorted = sorted((abs(p.weight) for p in positions), reverse=True)
    top_5 = sum(abs_sorted[:5]) / gross

    # Sector exposure
    per_sector: dict[str, float] = {}
    for p in positions:
        if not p.sector: continue
        per_sector[p.sector] = per_sector.get(p.sector, 0.0) + p.weight

    return {
        "hhi":            round(hhi, 4),
        "effective_n":    round(effective_n, 2),
        "top_5_pct":      round(top_5, 4),
        "per_sector_pct": {s: round(v, 4) for s, v in per_sector.items()},
        "n_sectors":      len({s for s in per_sector if abs(per_sector[s]) > 1e-9}),
        "n_long":         sum(1 for p in positions if p.weight > 0),
        "n_short":        sum(1 for p in positions if p.weight < 0),
    }

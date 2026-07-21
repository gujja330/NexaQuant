"""Portfolio construction: top-N selection + weight normalization.

Deterministic. Takes SizedPosition-shaped dicts (from Sprint 4 sized_positions.json)
and returns Position dicts ready for the PortfolioSnapshot.
"""
from __future__ import annotations

from backend.portfolio.types import Position


def build_portfolio(sized_positions: list[dict], target_n: int,
                      min_position_size: float, cash_reserve: float,
                      asof: str, market: str,
                      ticker_sector: dict[str, str] | None = None,
                      model_stamp: dict | None = None) -> list[Position]:
    """Turn sized positions into an investable portfolio.

    Steps:
      1. Drop positions with |target_weight| < min_position_size
      2. Sort by |confidence × target_weight| desc — highest-conviction first
      3. Take top-target_n
      4. Renormalize so sum(|w|) = (1 - cash_reserve)

    Deterministic — no random state; sort tiebreaker is ticker string.
    """
    if not sized_positions:
        return []

    # Keep only positions with meaningful size
    filtered = [
        p for p in sized_positions
        if p.get("target_weight") is not None
        and abs(float(p["target_weight"])) >= min_position_size
    ]
    if not filtered:
        return []

    # Sort by conviction (|confidence × weight|) desc, ticker asc for stable tiebreak
    def _conviction(p):
        w = float(p.get("target_weight") or 0)
        c = float(p.get("confidence") or 0)
        return (abs(w * c), -(hash(p.get("ticker") or "") % 10007))

    filtered.sort(key=_conviction, reverse=True)
    top = filtered[:target_n]

    # Renormalize gross exposure to (1 - cash_reserve)
    gross = sum(abs(float(p["target_weight"])) for p in top)
    if gross <= 0:
        return []
    target_gross = max(0.0, 1.0 - cash_reserve)
    scale = target_gross / gross if gross > 0 else 0.0

    ts = ticker_sector or {}
    stamp = dict(model_stamp) if model_stamp else {}

    positions: list[Position] = []
    for p in top:
        w = float(p["target_weight"]) * scale
        positions.append(Position(
            market=market,
            ticker=str(p["ticker"]),
            weight=round(w, 6),
            notional=0.0,
            entry_date=asof,
            entry_price=(float(p["entry_reference"])
                          if p.get("entry_reference") is not None else None),
            current_price=(float(p["entry_reference"])
                            if p.get("entry_reference") is not None else None),
            days_held=0,
            action_source=str((p.get("model_stamp") or {}).get("model_id",
                                  "aegis.recommendation.v3")),
            sector=str(ts.get(str(p["ticker"]), "")),
            stop_loss_pct=(float(p["stop_loss_pct"])
                            if p.get("stop_loss_pct") is not None else None),
            model_stamp=stamp,
        ))
    return positions

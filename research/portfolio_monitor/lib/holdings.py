"""DEV024 holdings loader + market-value refresh.

Holdings file schema:
{
    "portfolio_id": "...",
    "created_date": "YYYY-MM-DD",
    "cash": 500000,
    "total_invested_capital": 10000000,
    "holdings": [
        {"ticker": "...", "shares": N, "avg_cost": X,
         "target_weight": 0.05, "entry_date": "YYYY-MM-DD",
         "target_price": ..., "stop_loss": ..., "trailing_stop": ...,
         "recommendation_type": "Strong-Buy", "recommendation_source": "DEV023"}
    ]
}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"


@dataclass
class Position:
    ticker: str
    shares: int
    avg_cost: float
    entry_date: str
    target_weight: float

    latest_close: Optional[float] = None
    current_value: Optional[float] = None
    current_weight: Optional[float] = None
    unrealised_pnl_abs: Optional[float] = None
    unrealised_pnl_pct: Optional[float] = None
    days_held: Optional[int] = None

    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_stop: Optional[float] = None
    running_high: Optional[float] = None
    recommendation_type: Optional[str] = None
    recommendation_source: Optional[str] = None


@dataclass
class Portfolio:
    portfolio_id: str
    created_date: str
    cash: float
    total_invested_capital: float
    positions: list[Position]

    total_equity_value: float = 0.0
    total_portfolio_value: float = 0.0
    total_pnl_abs: float = 0.0
    total_pnl_pct: float = 0.0
    days_active: int = 0


def load_holdings(path: Path) -> Portfolio | None:
    if not path.exists():
        return None
    try:
        data = json.load(path.open("r", encoding="utf-8"))
    except Exception:
        return None
    positions = [Position(**{k: v for k, v in h.items()
                               if k in Position.__dataclass_fields__})
                 for h in data.get("holdings", [])]
    return Portfolio(
        portfolio_id=data.get("portfolio_id", "unknown"),
        created_date=data.get("created_date", ""),
        cash=float(data.get("cash", 0)),
        total_invested_capital=float(data.get("total_invested_capital", 0)),
        positions=positions,
    )


def _load_latest_close(ticker: str, running_high_since: str | None = None) -> tuple[float, float] | tuple[None, None]:
    """Return (latest_close, running_high_since_entry) or (None, None)."""
    p = CONSTITUENT_PARQ_DIR / f"{ticker}_D1.parquet"
    if not p.exists():
        return None, None
    try:
        df = pd.read_parquet(p)
        if df.empty or "close" not in df.columns:
            return None, None
        close = df["close"].dropna()
        if close.empty:
            return None, None
        latest = float(close.iloc[-1])
        rh = latest
        if running_high_since:
            since_ts = pd.Timestamp(running_high_since)
            since_slice = close.loc[close.index >= since_ts]
            if not since_slice.empty:
                rh = float(since_slice.max())
        return latest, rh
    except Exception:
        return None, None


def refresh_market_values(portfolio: Portfolio) -> Portfolio:
    """Populate current_value / current_weight / pnl on every position."""
    today = datetime.now(timezone.utc).date()
    total_equity = 0.0

    for pos in portfolio.positions:
        latest, running_high = _load_latest_close(pos.ticker, pos.entry_date)
        if latest is None:
            continue
        pos.latest_close = latest
        pos.running_high = running_high
        pos.current_value = latest * pos.shares
        total_equity += pos.current_value

        cost_basis = pos.avg_cost * pos.shares
        pos.unrealised_pnl_abs = pos.current_value - cost_basis
        pos.unrealised_pnl_pct = (
            (latest / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else None
        )

        try:
            entry_dt = pd.Timestamp(pos.entry_date).date()
            pos.days_held = (today - entry_dt).days
        except Exception:
            pos.days_held = None

    portfolio.total_equity_value = total_equity
    portfolio.total_portfolio_value = total_equity + portfolio.cash

    # Current weights from live equity
    if portfolio.total_portfolio_value > 0:
        for pos in portfolio.positions:
            if pos.current_value is not None:
                pos.current_weight = pos.current_value / portfolio.total_portfolio_value

    if portfolio.total_invested_capital > 0:
        portfolio.total_pnl_abs = portfolio.total_portfolio_value - portfolio.total_invested_capital
        portfolio.total_pnl_pct = (
            portfolio.total_portfolio_value / portfolio.total_invested_capital - 1
        ) * 100

    try:
        created = pd.Timestamp(portfolio.created_date).date()
        portfolio.days_active = (today - created).days
    except Exception:
        portfolio.days_active = None

    return portfolio


def synthesise_from_recommendations(recs_json: dict, portfolio_type: str = "top_10_ew",
                                       capital: float = 10_000_000,
                                       cash_reserve_pct: float = 0.05) -> dict:
    """Build a synthetic holdings.json from DEV023 recommendations.

    Used with --demo flag when the operator has no live portfolio.
    Picks top-conviction Strong-Buy/Buy recs, equal-weight, up to N positions."""
    recs = recs_json.get("recommendations", [])
    picks = [r for r in recs
              if r["recommendation"] in ("Strong-Buy", "Buy") and r.get("entry_exit")]
    picks.sort(key=lambda r: r["conviction_pct"], reverse=True)

    # Portfolio-type sizing
    n_map = {
        "top_5_ew":  5, "top_10_ew": 10, "top_20_ew": 20,
        "top_10":    10, "top_20":    20, "concentrated": 5,
    }
    n = n_map.get(portfolio_type, 10)
    picks = picks[:n]
    if not picks:
        return {}

    equity_capital = capital * (1 - cash_reserve_pct)
    per_position = equity_capital / len(picks)

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()

    holdings = []
    for r in picks:
        ee = r["entry_exit"]
        entry_px = ee["latest_close"]
        shares = int(per_position / entry_px)
        if shares <= 0:
            continue
        holdings.append({
            "ticker": r["ticker"],
            "shares": shares,
            "avg_cost": entry_px,
            "target_weight": 1.0 / len(picks),
            "entry_date": today,
            "recommendation_type": r["recommendation"],
            "recommendation_source": "DEV023",
            "target_price": ee["target_1"],
            "stop_loss": ee["stop_loss"],
            "trailing_stop": ee.get("trailing_stop_initial"),
        })

    return {
        "portfolio_id":            f"demo_{portfolio_type}_{today}",
        "created_date":            today,
        "cash":                    capital * cash_reserve_pct,
        "total_invested_capital":  capital,
        "holdings":                holdings,
    }

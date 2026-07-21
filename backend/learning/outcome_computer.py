"""Outcome computer — match closed recommendations to price outcomes.

Given a historical recommendation (rec_asof, ticker, entry_reference) and a
horizon (default 60 days), find the exit price on horizon_close_date from
the historical Feature Store or raw parquet, compute signed return, mark
winner/loser, and detect stop-loss / take-profit hits along the path.

Deterministic. No random state. Walk-forward safe (cutoff filters which
historical recommendations are considered).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from backend.learning.types import LearningRow, ErrorBucket


DEFAULT_HORIZON_DAYS = 60


def _load_price_series(repo_root: Path, market: str, ticker: str) -> pd.DataFrame:
    """Load the raw D1 parquet for a ticker. Empty DF if not found."""
    if market == "usa":
        p = Path(repo_root) / "usa" / "data" / "raw" / "us" / f"{ticker}_D1.parquet"
    else:
        p = Path(repo_root) / "data" / "raw" / "india" / f"{ticker}_D1.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    if df.index.name and df.index.name.lower() in ("date", "time", "datetime"):
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
    date_col = next((c for c in df.columns if c in ("date", "time", "datetime")), None)
    if date_col:
        df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date")


def _price_on_or_after(prices: pd.DataFrame, target: date) -> tuple[float | None, date | None]:
    """First price row on or after target date. Returns (close, date) or (None, None)."""
    if prices.empty: return None, None
    mask = prices["date"] >= pd.Timestamp(target)
    sub = prices[mask].head(1)
    if sub.empty: return None, None
    return float(sub["close"].iloc[0]), sub["date"].iloc[0].date()


def _path_between(prices: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if prices.empty: return prices
    mask = (prices["date"] >= pd.Timestamp(start)) & (prices["date"] <= pd.Timestamp(end))
    return prices[mask].reset_index(drop=True)


def _detect_stop_or_profit(path: pd.DataFrame, entry: float,
                              action: str, stop_loss_pct: float | None,
                              take_profit_pct: float | None) -> tuple[bool, bool]:
    if path.empty or entry <= 0:
        return False, False
    is_long = action.upper() in ("BUY", "STRONG_BUY")
    hit_stop = False; hit_take = False
    for _, r in path.iterrows():
        low  = float(r.get("low",  r["close"]))
        high = float(r.get("high", r["close"]))
        if is_long:
            if stop_loss_pct is not None:
                if (low / entry - 1) <= stop_loss_pct: hit_stop = True; break
            if take_profit_pct is not None:
                if (high / entry - 1) >= take_profit_pct: hit_take = True; break
        else:
            if stop_loss_pct is not None:
                if (high / entry - 1) >= abs(stop_loss_pct): hit_stop = True; break
            if take_profit_pct is not None:
                if (low / entry - 1) <= -abs(take_profit_pct): hit_take = True; break
    return hit_stop, hit_take


def compute_outcomes(repo_root: Path, market: str,
                       rec_history: pd.DataFrame,
                       cutoff: date | None = None,
                       horizon_days: int = DEFAULT_HORIZON_DAYS,
                       already_closed_keys: set | None = None) -> list[LearningRow]:
    """Compute outcomes for every recommendation whose horizon has closed on or before cutoff.

    Args:
      rec_history: append-only ledger of past recommendations. Must contain columns:
                    market, ticker, rec_asof, action, ensemble_score, calibrated_confidence,
                    regime, top_models (list), top_features (list),
                    entry_reference (price), stop_loss_pct, take_profit_pct,
                    model_stamp (dict), schema_fingerprint, feature_set_version.
      cutoff:       walk-forward cutoff — only consider recs whose horizon_close_date <= cutoff
      already_closed_keys: set of (market, ticker, rec_asof_iso) to skip (already in corpus)

    Returns:
      List of LearningRow — one per newly-closed recommendation.
    """
    if rec_history is None or rec_history.empty:
        return []
    if cutoff is None:
        cutoff = date.today()

    already = already_closed_keys or set()
    rows: list[LearningRow] = []

    for _, r in rec_history.iterrows():
        try:
            rec_asof = _parse_date(r.get("rec_asof") or r.get("asof"))
        except Exception:
            continue
        if rec_asof is None: continue

        horizon_close = rec_asof + timedelta(days=horizon_days)
        if horizon_close > cutoff:
            continue      # horizon hasn't closed yet at this cutoff

        ticker = str(r.get("ticker") or "")
        if not ticker: continue

        key = (market, ticker, rec_asof.isoformat())
        if key in already: continue      # already in corpus

        action = str(r.get("action") or "HOLD")
        if action == "HOLD": continue    # HOLDs don't generate outcomes

        prices = _load_price_series(repo_root, market, ticker)
        entry_ref = _to_float(r.get("entry_reference"))
        entry_price, entry_date = _price_on_or_after(prices, rec_asof)
        # Prefer the ref price recorded at rec time; fall back to first market close on/after rec_asof
        if entry_ref is not None and entry_ref > 0:
            entry_price = entry_ref
        if entry_price is None or entry_price <= 0:
            continue      # can't compute outcome without an entry

        exit_price, exit_date = _price_on_or_after(prices, horizon_close)
        if exit_price is None:
            # Horizon closed but no market data → skip until data lands
            continue

        # Signed return (positive = winner for the action direction)
        is_long = action in ("BUY", "STRONG_BUY")
        raw_return = exit_price / entry_price - 1.0
        signed_return = raw_return if is_long else -raw_return
        is_winner = signed_return > 0

        # Stop-loss / take-profit path checks
        path = _path_between(prices, rec_asof, horizon_close)
        hit_stop, hit_take = _detect_stop_or_profit(
            path, entry_price, action,
            _to_float(r.get("stop_loss_pct")),
            _to_float(r.get("take_profit_pct")),
        )

        # Coarse error bucket
        if is_winner:
            bucket = ErrorBucket.WORKED_AS_EXPECTED.value
        elif hit_stop:
            bucket = ErrorBucket.UNDERESTIMATED_VOL.value
        else:
            bucket = ErrorBucket.UNCLASSIFIED.value

        rows.append(LearningRow(
            market=market, ticker=ticker,
            rec_asof=rec_asof, horizon_close_date=horizon_close,
            action=action,
            ensemble_score=_to_float(r.get("ensemble_score")) or 0.0,
            calibrated_confidence=_to_float(r.get("calibrated_confidence"))
                                     or _to_float(r.get("regime_adjusted_confidence")) or 0.0,
            regime_at_rec=str(r.get("regime") or r.get("regime_at_rec") or "unknown"),
            entry_price=round(entry_price, 4),
            exit_price=round(exit_price, 4),
            return_pct=round(signed_return, 6),
            is_winner=bool(is_winner),
            horizon_days=int((exit_date - rec_asof).days) if exit_date else horizon_days,
            hit_stop_loss=hit_stop, hit_take_profit=hit_take,
            top_models=list(r.get("top_models") or []),
            top_features=list(r.get("top_features") or []),
            error_bucket=bucket,
            model_stamp_at_rec=dict(r.get("model_stamp") or {}),
            feature_set_version=str(r.get("feature_set_version") or ""),
            schema_fingerprint=str(r.get("schema_fingerprint") or ""),
        ))
    return rows


def _parse_date(x) -> date | None:
    if x is None or (isinstance(x, float) and pd.isna(x)): return None
    if isinstance(x, date) and not isinstance(x, (pd.Timestamp,)): return x
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None


def _to_float(x) -> float | None:
    if x is None or (isinstance(x, float) and pd.isna(x)): return None
    try: return float(x)
    except Exception: return None

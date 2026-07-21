"""Explainer — deterministic bull_case / bear_case / risks / entry / exit generator.

Reads a ticker's feature row + per-model score dict + action. Emits four
strings that a downstream engine or human can read:

  bull_case:  positive drivers currently supporting the call
  bear_case:  counter-signals that would invalidate the call
  key_risks:  list of concrete risks
  entry_zone: {low, high, current} price band
  exit_conditions: list of triggers that would flip the call

Sprint 3 ships template-based prose (no LLM). Deterministic on identical
input — walk-forward replay reproduces identical text.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.recommendation.types import Action


def _fmt(x, unit: str = "") -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a"
    if isinstance(x, (int, float)):
        if unit == "%":  return f"{x:+.2f}%"
        if unit == "$":  return f"${x:.2f}"
        return f"{x:.3f}"
    return str(x)


# ── Positive / negative interpretation helpers ─────────────────
def _bullish_signals(row: dict) -> list[str]:
    bits: list[str] = []
    if row.get("return_20d_pct") is not None and row["return_20d_pct"] > 5:
        bits.append(f"1-month momentum {_fmt(row['return_20d_pct'], '%')}")
    if row.get("return_60d_pct") is not None and row["return_60d_pct"] > 8:
        bits.append(f"3-month momentum {_fmt(row['return_60d_pct'], '%')}")
    if row.get("price_above_sma200") == 1 or row.get("price_above_sma200") == 1.0:
        bits.append("above 200-day moving average")
    if row.get("fund_quality_score") is not None and row["fund_quality_score"] > 65:
        bits.append(f"strong fundamental quality ({_fmt(row['fund_quality_score'])})")
    if row.get("fund_roe") is not None and row["fund_roe"] > 0.18:
        bits.append(f"high ROE ({_fmt(row['fund_roe'] * 100 if abs(row['fund_roe']) < 1 else row['fund_roe'], '%')})")
    if row.get("news_sentiment") is not None and row["news_sentiment"] > 0.15:
        bits.append(f"positive news sentiment ({_fmt(row['news_sentiment'])})")
    if row.get("insider_net_90d") is not None and row["insider_net_90d"] > 10_000_000:
        bits.append(f"net insider buying (${row['insider_net_90d']:,.0f}, 90d)")
    if row.get("sector_is_leader") in (1, 1.0):
        bits.append("sector is a top-3 leader this month")
    if row.get("mi_regime") == "bull":
        bits.append("market regime is bullish")
    return bits


def _bearish_signals(row: dict) -> list[str]:
    bits: list[str] = []
    if row.get("return_20d_pct") is not None and row["return_20d_pct"] < -5:
        bits.append(f"1-month drawdown {_fmt(row['return_20d_pct'], '%')}")
    if row.get("rsi_14") is not None and row["rsi_14"] > 75:
        bits.append(f"overbought RSI ({_fmt(row['rsi_14'])})")
    if row.get("rsi_14") is not None and row["rsi_14"] < 30:
        bits.append(f"oversold RSI ({_fmt(row['rsi_14'])}) — momentum broken")
    if row.get("fund_trailing_pe") is not None and row["fund_trailing_pe"] > 40:
        bits.append(f"stretched valuation (P/E {_fmt(row['fund_trailing_pe'])})")
    if row.get("fund_debt_to_equity") is not None and row["fund_debt_to_equity"] > 1.5:
        bits.append(f"high leverage (D/E {_fmt(row['fund_debt_to_equity'])})")
    if row.get("news_sentiment") is not None and row["news_sentiment"] < -0.15:
        bits.append(f"negative news sentiment ({_fmt(row['news_sentiment'])})")
    if row.get("insider_net_90d") is not None and row["insider_net_90d"] < -10_000_000:
        bits.append(f"net insider selling (${row['insider_net_90d']:,.0f}, 90d)")
    if row.get("max_drawdown_60d_pct") is not None and row["max_drawdown_60d_pct"] < -20:
        bits.append(f"deep 60d drawdown ({_fmt(row['max_drawdown_60d_pct'], '%')})")
    if row.get("mi_regime") in ("bear", "stress"):
        bits.append(f"market regime is {row['mi_regime']}")
    if row.get("macro_vix") is not None and row["macro_vix"] > 25:
        bits.append(f"volatility elevated (VIX {_fmt(row['macro_vix'])})")
    return bits


def _risks(row: dict, action: Action) -> list[str]:
    risks: list[str] = []
    if row.get("earn_days_to_next") is not None and 0 < row["earn_days_to_next"] < 21:
        risks.append(f"earnings in {int(row['earn_days_to_next'])} days — reduce position size ahead of print")
    if row.get("macro_vix") is not None and row["macro_vix"] > 22:
        risks.append("elevated market volatility increases false-signal risk")
    if row.get("adx_14") is not None and row["adx_14"] < 18:
        risks.append(f"weak trend strength (ADX {_fmt(row['adx_14'])}) — call may be premature")
    if action in (Action.BUY, Action.STRONG_BUY):
        if row.get("fund_debt_to_equity") is not None and row["fund_debt_to_equity"] > 1.0:
            risks.append("leverage above 1x amplifies downside if fundamentals slip")
    if action in (Action.SELL, Action.STRONG_SELL):
        if row.get("news_sentiment") is not None and row["news_sentiment"] > 0:
            risks.append("positive news backdrop could squeeze the short side")
    return risks


def _entry_zone(row: dict, action: Action) -> dict:
    current = row.get("close")
    if current is None:
        return {"low": None, "high": None, "current": None}
    if action in (Action.STRONG_BUY, Action.BUY):
        return {"low": round(current * 0.98, 3), "high": round(current * 1.02, 3),
                 "current": round(current, 3),
                 "note": "±2% band around current price"}
    if action in (Action.STRONG_SELL, Action.SELL):
        return {"low": round(current * 0.98, 3), "high": round(current * 1.02, 3),
                 "current": round(current, 3),
                 "note": "trim within ±2% band"}
    return {"current": round(current, 3), "note": "hold — no entry"}


def _exit_conditions(row: dict, action: Action, hold_days: int) -> list[str]:
    cond: list[str] = []
    if action in (Action.BUY, Action.STRONG_BUY):
        cond.append(f"time-based: review after {hold_days} days if action still holds")
        cond.append("price-based: 8% stop-loss from entry")
        cond.append("price-based: consider trimming +15% from entry")
        cond.append("thesis-based: exit if bull case signals invert (any 2 of them)")
    elif action in (Action.SELL, Action.STRONG_SELL):
        cond.append(f"time-based: reassess after {hold_days} days")
        cond.append("thesis-based: cover if bear case signals invert (any 2 of them)")
    else:
        cond.append("no active exit trigger — HOLD position")
    return cond


def explain(feature_row: dict, per_model_score: dict[str, float],
              action: Action, ensemble_score: float,
              suggested_holding_days: int) -> dict:
    """Return {bull_case, bear_case, key_risks, entry_zone, exit_conditions}."""
    bulls = _bullish_signals(feature_row)
    bears = _bearish_signals(feature_row)

    if bulls:
        bull_case = "; ".join(bulls) + "."
    else:
        bull_case = "no strong positive signals in the current feature snapshot."

    if bears:
        bear_case = "; ".join(bears) + "."
    else:
        bear_case = "no material negative signals right now."

    risks = _risks(feature_row, action)
    entry = _entry_zone(feature_row, action)
    exits = _exit_conditions(feature_row, action, suggested_holding_days)

    return {
        "bull_case":       bull_case,
        "bear_case":       bear_case,
        "key_risks":       risks,
        "entry_zone":      entry,
        "exit_conditions": exits,
    }

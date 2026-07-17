"""DEV030 · load strategy universe from earlier DEV outputs.

The strategy universe today = the 6 backtested strategies from DEV021.
Challenger candidates = the 99 constructions from DEV022 (for future promotion,
not for head-to-head ranking today, since they lack backtest history)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


def load_backtested_strategies() -> pd.DataFrame:
    """Return the DEV021 strategy metrics — one row per strategy."""
    p = REPORTS / "backtest_summary.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    # normalise column names — DEV021 uses annual_vol / max_dd_pct which differ from JSON schema
    return df.copy()


def load_equity_curves() -> pd.DataFrame:
    """One column per strategy of cumulative equity over time. Empty if missing.

    Accepts DEV021's long-format CSV [strategy, date, equity] and pivots it
    to wide format automatically."""
    p = REPORTS / "backtest_equity_curves.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    if df.empty:
        return df
    cols_lower = {c.lower(): c for c in df.columns}
    if "strategy" in cols_lower and "date" in cols_lower and "equity" in cols_lower:
        df = df.rename(columns={cols_lower["strategy"]: "strategy",
                                    cols_lower["date"]: "date",
                                    cols_lower["equity"]: "equity"})
        df["date"] = pd.to_datetime(df["date"])
        wide = df.pivot_table(index="date", columns="strategy", values="equity", aggfunc="last")
        wide = wide.sort_index()
        return wide
    # Fallback: assume already-wide format
    date_col = next((c for c in df.columns if c.lower() in ("date", "dt", "timestamp")), df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    return df


def load_current_regime() -> dict:
    """Global posture from DEV017 (Risk-On/Risk-Off/Neutral)."""
    p = REPORTS / "global_context.json"
    if not p.exists():
        return {"global_posture": "Unknown", "usd": "Unknown", "vol_regime": "Unknown"}
    try:
        with p.open("r", encoding="utf-8") as f:
            gc = json.load(f)
        c = gc.get("classifications", {}) or {}
        return {
            "global_posture": c.get("global_posture", "Unknown"),
            "usd":            c.get("usd", "Unknown"),
            "vol_regime":     c.get("vol_regime", "Unknown"),
        }
    except Exception:
        return {"global_posture": "Unknown", "usd": "Unknown", "vol_regime": "Unknown"}


def load_challenger_portfolios() -> pd.DataFrame:
    """DEV022 portfolio constructions — 99 rows (portfolio_type × allocator).

    Aggregated to one row per portfolio with construction-quality proxy metrics."""
    p = REPORTS / "portfolio.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if df.empty:
        return df

    def agg(g: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "n_positions":        int(g["ticker"].nunique()),
            "n_sectors":          int(g["sector"].nunique()),
            "n_industries":       int(g["industry"].nunique()),
            "avg_score":          float(g["score"].mean()),
            "avg_confidence":     float(g["confidence"].mean()),
            "max_weight":         float(g["weight"].max()),
            "top5_weight_share":  float(g.nlargest(5, "weight")["weight"].sum()),
            "hhi":                float((g["weight"] ** 2).sum()),
        })
    grouped = (df.groupby(["portfolio_type", "allocator"], as_index=False)
                .apply(agg, include_groups=False)
                .reset_index(drop=True))
    return grouped


def load_confidence_calibration_summary() -> dict:
    """DEV029 headline — used to flag if raw confidences are unreliable."""
    p = REPORTS / "confidence_calibration.json"
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

"""DEV030 · regime-conditional performance.

Splits each strategy's equity curve into calendar-based regime windows and
computes per-regime CAGR + volatility + max_dd + Sharpe.

Regime labels today come from DEV017 global_context (a single current label).
We do NOT have per-date historical regime labels persisted yet, so this
module falls back to a simple market-return-based classifier over the equity
window (positive rolling 6m NIFTY return -> Risk-On, negative -> Risk-Off,
otherwise Neutral) when historical labels are missing."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _daily_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().fillna(0.0)


def _annualise_return(daily_rets: pd.Series) -> float:
    if daily_rets.empty:
        return 0.0
    n_days = len(daily_rets)
    cum = float((1.0 + daily_rets).prod())
    if cum <= 0 or n_days == 0:
        return 0.0
    yrs = n_days / 252.0
    if yrs <= 0:
        return 0.0
    return float(cum ** (1.0 / yrs) - 1.0)


def _annualise_vol(daily_rets: pd.Series) -> float:
    if len(daily_rets) < 2:
        return 0.0
    return float(daily_rets.std() * np.sqrt(252))


def _max_dd(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = (equity / peak - 1.0)
    return float(dd.min())


def _sharpe(daily_rets: pd.Series) -> float:
    if daily_rets.std() == 0 or len(daily_rets) < 2:
        return 0.0
    return float(daily_rets.mean() / daily_rets.std() * np.sqrt(252))


def _label_by_market_return(equity_index: pd.DataFrame, window: int = 126) -> pd.Series:
    """Fallback regime labels from an equal-weight-universe benchmark curve.

    If a column named `ew_universe` exists it's used as the market proxy;
    otherwise the median of all curves at each timestamp."""
    if "ew_universe" in equity_index.columns:
        market = equity_index["ew_universe"]
    else:
        market = equity_index.median(axis=1)

    market = market.astype(float)
    rolling = market.pct_change(window).fillna(0.0)
    labels = pd.Series(index=market.index, dtype=object)
    labels[rolling > 0.03]  = "Risk-On"
    labels[rolling < -0.03] = "Risk-Off"
    labels[labels.isna()]   = "Neutral"
    return labels


def compare(equity_curves: pd.DataFrame, current_regime_label: str = "Unknown") -> dict:
    """Return regime-conditional metrics per strategy.

    Structure:
        {
          "current_regime": "Risk-On",
          "regime_windows": {"Risk-On": {"n_days": 180, ...}, ...},
          "per_strategy": {
            strategy_name: {
              "Risk-On": {"cagr":..., "vol":..., "sharpe":..., "max_dd":..., "n_days":...},
              "Risk-Off": {...}, "Neutral": {...},
            }, ...
          },
          "regime_champions": {"Risk-On": strategy, "Risk-Off": ...},
        }
    """
    if equity_curves.empty:
        return {
            "current_regime":   current_regime_label,
            "regime_windows":   {},
            "per_strategy":     {},
            "regime_champions": {},
            "source":           "no equity curves available",
        }

    labels = _label_by_market_return(equity_curves)
    counts = labels.value_counts().to_dict()

    per_strategy = {}
    for col in equity_curves.columns:
        curve = equity_curves[col].dropna()
        if curve.empty:
            continue
        per_strategy[col] = {}
        for label in ["Risk-On", "Risk-Off", "Neutral"]:
            mask = labels.reindex(curve.index) == label
            n_days = int(mask.sum())
            if n_days < 20:
                per_strategy[col][label] = {"n_days": n_days, "cagr": None,
                                             "vol": None, "sharpe": None, "max_dd": None}
                continue
            sub = curve[mask]
            rets = _daily_returns(sub)
            per_strategy[col][label] = {
                "n_days": n_days,
                "cagr":   round(_annualise_return(rets), 4),
                "vol":    round(_annualise_vol(rets), 4),
                "sharpe": round(_sharpe(rets), 4),
                "max_dd": round(_max_dd(sub), 4),
            }

    # regime champion per label = highest cagr strategy in that regime with n_days >= 20
    regime_champions = {}
    for label in ["Risk-On", "Risk-Off", "Neutral"]:
        best_name, best_cagr = None, -np.inf
        for strat, by_regime in per_strategy.items():
            r = by_regime.get(label, {})
            c = r.get("cagr")
            if c is None:
                continue
            if c > best_cagr:
                best_cagr, best_name = c, strat
        if best_name is not None:
            regime_champions[label] = {"strategy": best_name,
                                        "cagr": round(float(best_cagr), 4)}

    return {
        "current_regime":   current_regime_label,
        "regime_source":    "fallback: 6m market-return classifier",
        "regime_windows":   {k: int(v) for k, v in counts.items()},
        "per_strategy":     per_strategy,
        "regime_champions": regime_champions,
    }

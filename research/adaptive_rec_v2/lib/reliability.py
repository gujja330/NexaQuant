"""Adaptive Rec v2.0 · reliability curves per confidence tier."""
from __future__ import annotations

import numpy as np


def reliability_curve(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list[dict]:
    if len(p) == 0:
        return []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        if n == 0:
            rows.append({"bin_lo": float(lo), "bin_hi": float(hi), "n": 0,
                          "predicted": None, "observed": None, "gap": None})
        else:
            avg_p = float(p[mask].mean())
            avg_y = float(y[mask].mean())
            rows.append({"bin_lo": float(lo), "bin_hi": float(hi), "n": n,
                          "predicted": round(avg_p, 4),
                          "observed": round(avg_y, 4),
                          "gap": round(avg_p - avg_y, 4)})
    return rows


def tier_discrimination(p: np.ndarray, y: np.ndarray, returns: np.ndarray | None = None) -> dict:
    """Reports win-rate and (optionally) expectancy at Strong-Buy / Buy / Hold / Sell tiers.

    Tiers correspond to how DEV023 buckets recommendations:
      Strong-Buy: top 5%
      Buy:        top 5-20%
      Hold:       middle 20-50%
      Sell:       bottom 50%+
    (percentiles of predicted score, not of raw confidence)."""
    if len(p) == 0:
        return {}
    order = np.argsort(-p)
    n = len(p)
    n_strong = max(1, int(n * 0.05))
    n_buy    = max(1, int(n * 0.15))
    n_hold   = max(1, int(n * 0.30))

    tiers = {
        "Strong-Buy":   order[:n_strong],
        "Buy":          order[n_strong: n_strong + n_buy],
        "Hold":         order[n_strong + n_buy: n_strong + n_buy + n_hold],
        "Sell":         order[n_strong + n_buy + n_hold:],
    }

    result = {}
    for tier, idx in tiers.items():
        if len(idx) == 0:
            continue
        wr = float(y[idx].mean())
        row = {
            "n":         int(len(idx)),
            "win_rate":  round(wr, 4),
            "predicted_mean": round(float(p[idx].mean()), 4),
        }
        if returns is not None:
            row["expectancy"] = round(float(returns[idx].mean()), 4)
        result[tier] = row
    return result


def discrimination_summary(tiers: dict) -> dict:
    """Test the DONE condition from PHASE2_MASTER_ROADMAP.md §6 Adaptive v2.0:
       Strong-Buy WR > Buy WR > Hold WR > Sell WR."""
    order = ["Strong-Buy", "Buy", "Hold", "Sell"]
    wrs = [tiers.get(t, {}).get("win_rate") for t in order]
    if any(w is None for w in wrs):
        return {"monotone_decreasing": False, "reason": "missing tier", "win_rates": wrs}

    monotone = (wrs[0] >= wrs[1] >= wrs[2] >= wrs[3])
    spread = wrs[0] - wrs[3]
    return {
        "monotone_decreasing":     bool(monotone),
        "strong_buy_win_rate":     wrs[0],
        "buy_win_rate":            wrs[1],
        "hold_win_rate":           wrs[2],
        "sell_win_rate":           wrs[3],
        "top_bottom_spread":       round(spread, 4),
        "verdict":                 ("PASS · discrimination present" if monotone and spread >= 0.10
                                     else "FAIL · discrimination weak" if not monotone
                                     else "MARGINAL · monotone but thin spread"),
    }

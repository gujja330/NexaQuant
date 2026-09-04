"""P4 · Cap × Sector Interaction Study.

Reads outcome_dataset · groups closed positions by (cap, sector) · reports
tier-safe cell metrics + nested-model likelihood-ratio test (Cap-only vs
Cap+Sector) to determine whether Sector adds information beyond Cap alone.

Governance · pure reporting · no threshold gets applied to R2. Result feeds
downstream P2/P3 upgrade decisions ONCE F01-F05 substrate matures.
"""
from __future__ import annotations
import json
import math
from datetime import datetime
from pathlib import Path


def _sample_tier(n: int) -> str:
    if n < 5: return "observation"
    if n < 15: return "hypothesis"
    if n < 30: return "research_signal"
    if n < 50: return "stronger_evidence"
    return "validation_candidate"


def _logistic_ll(y: list[int], p: list[float]) -> float:
    """Log-likelihood for binary y with predicted p (both same length)."""
    ll = 0.0
    eps = 1e-12
    for yi, pi in zip(y, p):
        pi = max(eps, min(1 - eps, pi))
        ll += (yi * math.log(pi) + (1 - yi) * math.log(1 - pi))
    return ll


def _fit_intercept_only(y: list[int]) -> tuple[float, float]:
    """Return (log_lik, predicted p) for intercept-only baseline."""
    p_hat = sum(y) / len(y) if y else 0.5
    ll = _logistic_ll(y, [p_hat] * len(y))
    return ll, p_hat


def _fit_by_group(y: list[int], groups: list[str]) -> tuple[float, dict]:
    """Fit per-group mean · log-likelihood + group-level p."""
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for yi, g in zip(y, groups):
        buckets[g].append(yi)
    p_by_group = {g: sum(vs) / len(vs) for g, vs in buckets.items()}
    preds = [p_by_group.get(g, 0.5) for g in groups]
    ll = _logistic_ll(y, preds)
    return ll, p_by_group


def compute_interaction_table(root: Path) -> dict:
    """Run the interaction study on outcome_dataset · both markets pooled."""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset.parquet"
    if not p.exists():
        return {"status": "MISSING", "reason": "outcome_dataset.parquet not found"}
    df = pd.read_parquet(p)
    closed = df[(df["is_closed"] == True) & (df["win_flag"].notna())]
    if len(closed) < 30:
        return {"status": "INSUFFICIENT_SAMPLE",
                 "n_closed": int(len(closed)), "required": 30}

    y = [1 if v else 0 for v in closed["win_flag"].tolist()]
    caps = [str(c) for c in closed["cap"].fillna("UNKNOWN").tolist()]
    secs = [str(s) for s in closed["sector"].fillna("UNKNOWN").tolist()]
    cap_sec = [f"{c}·{s}" for c, s in zip(caps, secs)]

    # Cells (cap, sector)
    from collections import defaultdict
    cells = defaultdict(list)
    for yi, c, s in zip(y, caps, secs):
        cells[(c, s)].append(yi)

    cell_rows = []
    for (c, s), vals in cells.items():
        n = len(vals); wr = sum(vals) / n
        cell_rows.append({"cap": c, "sector": s, "n": n,
                           "win_rate": round(wr, 4),
                           "sample_tier": _sample_tier(n)})
    cell_rows.sort(key=lambda x: -x["n"])

    # Nested-model LR test · Cap-only vs Cap+Sector
    ll_intercept, _ = _fit_intercept_only(y)
    ll_cap, _ = _fit_by_group(y, caps)
    ll_cap_sec, _ = _fit_by_group(y, cap_sec)

    lr_cap_over_intercept = 2 * (ll_cap - ll_intercept)
    lr_capsec_over_cap = 2 * (ll_cap_sec - ll_cap)

    # Approximate p using Wilson-Hilferty
    def _chi2_sf(x: float, k: int) -> float:
        if x <= 0 or k <= 0: return 1.0
        z = ((x / k) ** (1/3) - (1 - 2/(9*k))) / math.sqrt(2/(9*k))
        return 0.5 * math.erfc(z / math.sqrt(2))

    df_cap_sec_over_cap = max(1, len(set(cap_sec)) - len(set(caps)))
    p_lr = _chi2_sf(lr_capsec_over_cap, df_cap_sec_over_cap)

    return {
        "status": "OK",
        "n_closed_positions": int(len(closed)),
        "n_cells": len(cell_rows),
        "cells_top10_by_n": cell_rows[:10],
        "log_likelihood": {
            "intercept_only": round(ll_intercept, 3),
            "cap_only": round(ll_cap, 3),
            "cap_plus_sector": round(ll_cap_sec, 3),
        },
        "likelihood_ratio_test": {
            "H0": "Cap alone", "H1": "Cap + Sector",
            "lr_stat": round(lr_capsec_over_cap, 4),
            "df": df_cap_sec_over_cap,
            "p_value_approx": round(p_lr, 4),
            "sector_adds_info_beyond_cap_at_p_0.05": p_lr < 0.05,
        },
        "governance": ("V2 §P4 · reporting only · no threshold applied to R2 · "
                        "informs downstream P2/P3 upgrade decisions after F01-F05 mature"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_report(root: Path) -> Path:
    r = compute_interaction_table(root)
    out = root / "reports" / "research" / "r2_upgrades" / "p4_cap_sector_interaction.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    return out

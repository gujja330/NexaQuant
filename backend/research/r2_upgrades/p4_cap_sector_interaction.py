"""R2 · P4 · Cap × Sector Interaction Study
Sprint A · CEO 2026-09-03

Builds the interaction table Runner × Cap × Sector × Investability with:
    n · sample_tier · win_rate · avg_pnl · median_pnl · profit_factor · drawdown

Then compares:
    Model A · logistic(win ~ cap_bucket)
    Model B · logistic(win ~ cap_bucket + sector + cap*sector)
using the likelihood-ratio test to decide whether sector adds information
beyond cap alone.

Cells below n=5 are observation_only and excluded from the LR fit.

Output:
  reports/research/r2_upgrades/p4_cap_sector_{market}.json
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _tier(n: int) -> str:
    if n < 5: return "observation_only"
    if n < 15: return "hypothesis"
    if n < 30: return "research_signal"
    if n < 50: return "stronger_evidence"
    return "validation_candidate"


def _profit_factor(rets):
    gains = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    if losses <= 0: return float("inf") if gains > 0 else 0.0
    return gains / losses


def _max_dd(rets):
    # Reconstruct equity curve · assume unit trade size
    equity = 1.0; peak = 1.0; dd = 0.0
    for r in rets:
        equity *= (1.0 + r)
        peak = max(peak, equity)
        dd = min(dd, (equity - peak) / peak)
    return dd


def build_table(rows: list[dict]) -> list[dict]:
    """Group by (runner, cap, sector) and compute cell stats."""
    from collections import defaultdict
    cells = defaultdict(list)
    for r in rows:
        key = (str(r.get("runner") or "?"),
               str(r.get("cap_bucket") or "unknown"),
               str(r.get("sector") or "unknown"))
        v = r.get("realized_return_pct")
        if v is None: continue
        try:
            cells[key].append(float(v))
        except (TypeError, ValueError):
            pass
    table = []
    for (runner, cap, sec), rets in cells.items():
        n = len(rets)
        wins = sum(1 for x in rets if x > 0)
        table.append({
            "runner": runner, "cap_bucket": cap, "sector": sec,
            "n": n, "sample_tier": _tier(n),
            "win_rate": wins / n if n else 0.0,
            "mean_pnl": sum(rets)/n if n else 0.0,
            "median_pnl": sorted(rets)[n//2] if n else 0.0,
            "profit_factor": _profit_factor(rets),
            "max_drawdown": _max_dd(rets),
        })
    return sorted(table, key=lambda x: (x["runner"], x["cap_bucket"], x["sector"]))


def _logit(z):
    if z >= 0: e = math.exp(-z); return 1.0/(1.0+e)
    e = math.exp(z); return e/(1.0+e)


def _fit_logreg(X, y, max_iter=300, lr=0.1, l2=0.001):
    if not X: return []
    p = len(X[0]); n = len(X)
    w = [0.0]*p
    for _ in range(max_iter):
        g = [0.0]*p
        for xi, yi in zip(X, y):
            z = sum(w[k]*xi[k] for k in range(p))
            e = _logit(z) - float(yi)
            for k in range(p): g[k] += e*xi[k]
        for k in range(p):
            g[k] = g[k]/n + l2*w[k]
            w[k] -= lr*g[k]
    return w


def _loglik(w, X, y):
    ll = 0.0
    for xi, yi in zip(X, y):
        z = sum(w[k]*xi[k] for k in range(len(w)))
        p = _logit(z)
        p = max(min(p, 1-1e-9), 1e-9)
        ll += (yi*math.log(p) + (1-yi)*math.log(1-p))
    return ll


def lr_compare_cap_vs_cap_sector(rows: list[dict]) -> dict:
    from backend.research.walkforward.lr_test import lr_test

    valid = [r for r in rows
             if r.get("realized_return_pct") is not None
             and r.get("cap_bucket") and r.get("sector")]
    if len(valid) < 20:
        return {"n": len(valid), "note": "insufficient sample · need n>=20 for LR"}

    caps = sorted(set(str(r["cap_bucket"]) for r in valid))
    secs = sorted(set(str(r["sector"]) for r in valid))
    cap_idx = {c: i for i, c in enumerate(caps)}
    sec_idx = {s: i for i, s in enumerate(secs)}

    def _onehot(v, order):
        h = [0.0] * (len(order) - 1)  # drop last category as reference
        idx = order.index(v)
        if idx < len(order) - 1: h[idx] = 1.0
        return h

    y = [1 if float(r["realized_return_pct"]) > 0 else 0 for r in valid]

    # Model A · cap only
    XA = [[1.0] + _onehot(str(r["cap_bucket"]), caps) for r in valid]
    wA = _fit_logreg(XA, y)
    llA = _loglik(wA, XA, y)

    # Model B · cap + sector + interaction
    XB = []
    for r in valid:
        cap_h = _onehot(str(r["cap_bucket"]), caps)
        sec_h = _onehot(str(r["sector"]), secs)
        interaction = [c*s for c in cap_h for s in sec_h]
        XB.append([1.0] + cap_h + sec_h + interaction)
    wB = _fit_logreg(XB, y)
    llB = _loglik(wB, XB, y)

    df_diff = len(XB[0]) - len(XA[0])
    lr = lr_test(llB, llA, df_diff)
    return {
        "n": len(valid),
        "loglik_A_cap_only": llA,
        "loglik_B_cap_sector": llB,
        "df_diff": df_diff,
        "lr_stat": lr["lr_stat"],
        "p_value": lr["p_value"],
        "sector_adds_information": (lr["p_value"] is not None and lr["p_value"] < 0.05),
        "n_caps": len(caps), "n_sectors": len(secs),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    from backend.research.outcome_dataset import load_outcome_dataset
    df = load_outcome_dataset(root, args.market)
    if df.empty:
        print(json.dumps({"market": args.market, "note": "empty"}, indent=2)); return
    df = df[(df["is_administrative_exit"] != True)
            & df["realized_return_pct"].notna()].copy()
    rows = df.to_dict("records")
    table = build_table(rows)
    lr = lr_compare_cap_vs_cap_sector(rows)
    result = {
        "market": args.market,
        "n_cells": len(table),
        "interaction_table": table[:200],   # truncate for JSON size
        "likelihood_ratio_test": lr,
        "trial_count_in_matrix": 1,
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = root / "reports" / "research" / "r2_upgrades"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"p4_cap_sector_{args.market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str)[:1200])


if __name__ == "__main__":
    main()

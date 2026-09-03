"""R2 · P5 · Remaining Upgrades (five sub-items)
Sprint A · CEO 2026-09-03

P5.1 · Ensemble disagreement → sizing
P5.2 · Regime-conditional ensemble weights
P5.3 · Daily turnover cap + alpha-delta priority queue
P5.4 · PIT universe audit                (shipped separately · backend/research/pit_universe/)
P5.5 · Standing comparator               (equal-weight top-10 · 3-mo momentum · monthly rebalance)

Each sub-item is a self-contained function called by main() per --which arg.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


# ============ P5.1 · Disagreement → Sizing ============

def p5_1_disagreement_sizing(rows: list[dict]) -> dict:
    """Compute normalized stdev across model scores per position and its
    correlation with |realized_return - predicted_return|.

    If correlation > 0 and n >= 50 · size = base_size × (1 − disagreement).
    """
    valid = [r for r in rows if r.get("model_agreement") is not None
             and r.get("realized_return_pct") is not None
             and r.get("entry_signal_score") is not None]
    if len(valid) < 30:
        return {"n": len(valid), "gate_status": "INSUFFICIENT_SAMPLE"}

    # disagreement proxy · (1 - model_agreement) rescaled to [0,1]
    disagreement = [1.0 - float(r["model_agreement"]) for r in valid]
    errs = [abs(float(r["realized_return_pct"]) - float(r["entry_signal_score"])) for r in valid]

    # Pearson correlation
    def _pearson(x, y):
        n = len(x)
        mx = sum(x)/n; my = sum(y)/n
        num = sum((x[i]-mx)*(y[i]-my) for i in range(n))
        dx = math.sqrt(sum((v-mx)**2 for v in x))
        dy = math.sqrt(sum((v-my)**2 for v in y))
        return num/(dx*dy) if dx*dy > 0 else 0.0
    corr = _pearson(disagreement, errs)

    return {
        "n": len(valid),
        "corr_disagreement_vs_abs_error": corr,
        "size_formula": "base_size * (1 - disagreement)"
                        if corr > 0 else "no lift · retain base sizing",
        "gate_pass": corr > 0.05 and len(valid) >= 50,
        "sub_item": "P5.1",
    }


# ============ P5.2 · Regime-conditional weights ============

def p5_2_regime_weights(rows: list[dict], min_n_regime: int = 30) -> dict:
    """Group outcomes by regime and per model compute mean-score-times-win.

    If a regime has < min_n_regime trades, fall back to global weights."""
    from collections import defaultdict
    by_regime = defaultdict(list)
    for r in rows:
        reg = str(r.get("regime_at_entry") or "UNKNOWN")
        if r.get("realized_return_pct") is None: continue
        by_regime[reg].append(r)

    weights = {}
    for reg, batch in by_regime.items():
        n = len(batch)
        if n < min_n_regime:
            weights[reg] = {"policy": "USE_GLOBAL",
                            "n": n, "reason": f"n < {min_n_regime}"}
            continue
        # Approximate per-regime IC · mean sign-agreement between entry_signal_score and realized_ret
        agrees = sum(1 for r in batch
                     if r.get("entry_signal_score") is not None and
                     float(r.get("entry_signal_score", 0.0)) * float(r["realized_return_pct"]) > 0)
        weights[reg] = {"policy": "REGIME_SPECIFIC", "n": n,
                        "sign_agreement": agrees / n if n else 0.0}
    return {"per_regime": weights, "sub_item": "P5.2"}


# ============ P5.3 · Turnover cap ============

def p5_3_turnover_cap(candidate_signals: list[dict], nav: float,
                      cap_pct: float = 0.02) -> dict:
    """Rank candidates by expected alpha delta, execute until budget hits
    cap_pct * nav, defer remainder to next day queue.

    candidate_signals · each { ticker, expected_alpha_delta, size_dollars }
    """
    budget = nav * cap_pct
    ranked = sorted(candidate_signals,
                    key=lambda x: -float(x.get("expected_alpha_delta", 0.0)))
    executed = []
    deferred = []
    spent = 0.0
    for s in ranked:
        sz = float(s.get("size_dollars", 0.0))
        if spent + sz <= budget:
            executed.append(s); spent += sz
        else:
            deferred.append(s)
    return {
        "cap_pct": cap_pct, "nav": nav, "budget": budget,
        "n_candidates": len(ranked),
        "n_executed": len(executed), "n_deferred": len(deferred),
        "spent_dollars": spent, "spent_pct_nav": spent / nav if nav else 0.0,
        "sub_item": "P5.3",
    }


# ============ P5.5 · Standing Comparator (equal-weight top-10 3-mo momentum) ============

def p5_5_standing_comparator_returns(prices_by_ticker: dict, asof: str,
                                     universe: list[str], top_n: int = 10,
                                     lookback_months: int = 3) -> dict:
    """Compute equal-weighted top-N by 3-mo total return from `asof`.

    PERMANENT · never optimized · CEO 2026-09-03 · single yardstick for
    every future R2 change · lives in code, not in a tunable config.
    """
    import pandas as pd
    asof_dt = pd.to_datetime(asof).normalize()
    lookback_start = asof_dt - pd.DateOffset(months=lookback_months)

    momos = []
    for t in universe:
        df = prices_by_ticker.get(t)
        if df is None or df.empty: continue
        try:
            past = df[df.index <= lookback_start].tail(1)
            now = df[df.index <= asof_dt].tail(1)
            if past.empty or now.empty: continue
            r = (float(now["close"].iloc[-1]) / float(past["close"].iloc[-1])) - 1.0
            momos.append({"ticker": t, "mom_3mo": r})
        except Exception:
            continue

    momos.sort(key=lambda x: -x["mom_3mo"])
    picks = momos[:top_n]
    equal_weight_ret = sum(p["mom_3mo"] for p in picks) / len(picks) if picks else 0.0

    return {
        "asof": asof,
        "picks": picks,
        "equal_weight_3mo_return": equal_weight_ret,
        "lookback_months": lookback_months,
        "top_n": top_n,
        "rule": "PERMANENT · never optimized · monthly rebalance",
        "sub_item": "P5.5",
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", choices=("p5_1", "p5_2", "p5_3", "p5_5", "all"),
                    default="all")
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()

    root = Path(args.root)
    from backend.research.outcome_dataset import load_outcome_dataset
    df = load_outcome_dataset(root, args.market)
    if df.empty:
        print(json.dumps({"note": "outcome empty"}, indent=2)); return
    df = df[(df["is_administrative_exit"] != True)
            & df["realized_return_pct"].notna()].copy()
    rows = df.to_dict("records")

    result = {"market": args.market,
              "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    if args.which in ("p5_1", "all"):
        result["P5_1"] = p5_1_disagreement_sizing(rows)
    if args.which in ("p5_2", "all"):
        result["P5_2"] = p5_2_regime_weights(rows)
    if args.which in ("p5_3", "all"):
        # Simulated candidate stream for illustration
        result["P5_3_illustration"] = p5_3_turnover_cap(
            candidate_signals=[
                {"ticker": r["ticker"], "expected_alpha_delta": abs(float(r.get("entry_signal_score") or 0)),
                 "size_dollars": 10000}
                for r in rows[:50]
            ],
            nav=1_000_000.0,
        )
    if args.which in ("p5_5", "all"):
        result["P5_5"] = {"note": "call p5_5_standing_comparator_returns() with prices_by_ticker + universe"}

    out = root / "reports" / "research" / "r2_upgrades"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"p5_{args.market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str)[:1500])


if __name__ == "__main__":
    main()

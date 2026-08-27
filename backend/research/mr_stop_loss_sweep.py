"""AEGIS · M-R · Stop-Loss Policy Sweep · Sprint M Phase C.

For every enriched autopsy row, simulate what the outcome would have been
under each stop policy · using ONLY prediction-time features + parquet
close series after prediction date (which is the true forward window we
already read for MFE/MAE).

Policies:
   CURRENT        · whatever stop was stamped at prediction time (if any)
   FIXED_3        · 3% fixed stop below entry
   FIXED_5        · 5%
   FIXED_7_5      · 7.5%
   FIXED_10       · 10%
   ATR_2X         · 2 * 20D-vol from close, applied as pct
   ATR_3X         · 3 * 20D-vol
   VOL_ADAPTIVE   · 5% if vol_20d < 2%, 7.5% if 2-3%, 10% if >3%
   TRAILING_5     · 5% below the running max close
   TRAILING_10    · 10% below running max
   TIME_STOP_5D   · exit at fwd_5d if not stopped
   TIME_STOP_10D  · exit at fwd_10d if not stopped

Outcome recorded per (row, policy):
   final_pct       · realized % from entry to first stop-hit / horizon end
   stopped         · True/False
   days_held       · trading days until exit
   was_winner_at_exit
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT
from backend.research.mr_prediction_autopsy import _load_parquet

ENGINE_ID = "aegis.mr_stop_loss_sweep.v0.1"

WIN = 0.5
LOSS = -0.5
MAX_HOLD = 20    # trading days


POLICIES = [
    "CURRENT", "FIXED_3", "FIXED_5", "FIXED_7_5", "FIXED_10",
    "ATR_2X", "ATR_3X", "VOL_ADAPTIVE",
    "TRAILING_5", "TRAILING_10",
    "TIME_STOP_5D", "TIME_STOP_10D",
]


def _stop_pct_for(row: dict, policy: str) -> Optional[float]:
    """Return stop distance as NEGATIVE pct from entry."""
    ep = row.get("entry_price_at_pred")
    if policy == "CURRENT":
        st = row.get("stop_at_pred")
        if ep and st and st > 0:
            return (st - ep) / ep * 100
        return None
    if policy == "FIXED_3":   return -3.0
    if policy == "FIXED_5":   return -5.0
    if policy == "FIXED_7_5": return -7.5
    if policy == "FIXED_10":  return -10.0
    v = row.get("vol_20d_pct")
    if policy == "ATR_2X":    return -2 * v if v is not None else None
    if policy == "ATR_3X":    return -3 * v if v is not None else None
    if policy == "VOL_ADAPTIVE":
        if v is None: return None
        if v < 2:  return -5.0
        if v < 3:  return -7.5
        return -10.0
    return None  # trailing / time handled below


def _simulate(row: dict, pair, policy: str) -> dict:
    if pair is None: return {"policy": policy, "eligible": False}
    df, col = pair
    dates = sorted(df.index)
    iso = row.get("prediction_date","")
    if iso not in df.index:
        earlier = [d for d in dates if d <= iso]
        if not earlier: return {"policy": policy, "eligible": False}
        i0 = dates.index(earlier[-1])
    else:
        i0 = dates.index(iso)
    end = min(i0 + MAX_HOLD, len(dates) - 1)
    window = dates[i0:end+1]
    if len(window) < 2: return {"policy": policy, "eligible": False}
    p0 = float(df.loc[dates[i0], col])
    if p0 <= 0: return {"policy": policy, "eligible": False}
    closes = [float(df.loc[d, col]) for d in window]
    stop_pct = _stop_pct_for(row, policy)
    stopped = False
    stop_day = None
    final_pct = None
    if policy in ("TRAILING_5", "TRAILING_10"):
        trail = 5.0 if policy == "TRAILING_5" else 10.0
        running_max = closes[0]
        for i, c in enumerate(closes[1:], start=1):
            running_max = max(running_max, c)
            drop_pct = (c - running_max) / running_max * 100
            if drop_pct <= -trail:
                stopped = True
                stop_day = i
                final_pct = (c - p0) / p0 * 100
                break
        if not stopped:
            final_pct = (closes[-1] - p0) / p0 * 100
            stop_day = len(closes) - 1
    elif policy in ("TIME_STOP_5D", "TIME_STOP_10D"):
        horizon = 5 if policy == "TIME_STOP_5D" else 10
        end_i = min(horizon, len(closes) - 1)
        final_pct = (closes[end_i] - p0) / p0 * 100
        stop_day = end_i
    else:
        if stop_pct is None:
            return {"policy": policy, "eligible": False}
        for i, c in enumerate(closes[1:], start=1):
            pct = (c - p0) / p0 * 100
            if pct <= stop_pct:
                stopped = True
                stop_day = i
                final_pct = pct
                break
        if not stopped:
            final_pct = (closes[-1] - p0) / p0 * 100
            stop_day = len(closes) - 1
    return {
        "policy": policy,
        "eligible": True,
        "stopped": stopped,
        "days_held": stop_day,
        "final_pct": round(final_pct, 3),
    }


def _agg_policy(sims_for_policy: list) -> dict:
    if not sims_for_policy: return {"n": 0}
    finals = [s["final_pct"] for s in sims_for_policy]
    wins = sum(1 for f in finals if f > WIN)
    losers = [f for f in finals if f < LOSS]
    winners = [f for f in finals if f > WIN]
    stopped = sum(1 for s in sims_for_policy if s.get("stopped"))
    catastrophic = sum(1 for f in finals if f < -10.0)
    profit = sum(f for f in finals if f > 0)
    loss   = -sum(f for f in finals if f < 0)
    return {
        "n":                 len(finals),
        "wr_pct":            round(wins/len(finals)*100, 2),
        "avg_pct":           round(mean(finals), 3),
        "median_pct":        round(median(finals), 3),
        "avg_winner_pct":    round(mean(winners), 3) if winners else None,
        "avg_loser_pct":     round(mean(losers), 3) if losers else None,
        "profit_factor":     round(profit/loss, 3) if loss else None,
        "stop_hit_rate_pct": round(stopped/len(sims_for_policy)*100, 2),
        "catastrophic_gt10pct_pct":
                             round(catastrophic/len(finals)*100, 2),
        "expectancy_pct":    round(mean(finals), 3),
        "worst_pct":         round(min(finals), 3),
        "best_pct":          round(max(finals), 3),
        "avg_days_held":     round(mean(s["days_held"] for s in sims_for_policy
                                       if s.get("days_held") is not None), 2)
                             if any(s.get("days_held") is not None for s in sims_for_policy) else None,
    }


def run_market(root: Path, market: str) -> dict:
    src = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not src.exists():
        src = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not src.exists(): return {}
    rows = [json.loads(ln) for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    per_policy = defaultdict(list)
    per_policy_runner: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        pair = _load_parquet(root, r.get("ticker",""), market)
        for pol in POLICIES:
            s = _simulate(r, pair, pol)
            if s.get("eligible"):
                per_policy[pol].append(s)
                per_policy_runner[pol][r.get("runner","?")].append(s)
    return {
        "engine":       ENGINE_ID,
        "market":       market.upper(),
        "n_rows":       len(rows),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "by_policy":    {p: _agg_policy(per_policy[p]) for p in POLICIES},
        "by_policy_runner": {
            p: {run: _agg_policy(sims) for run, sims in v.items()}
            for p, v in per_policy_runner.items()
        },
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_stop_loss_sweep_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res: return
    print(f"\n======== STOP-LOSS SWEEP · {res['market']} · n={res['n_rows']} ========")
    print(f"  {'policy':14s} {'n':>4s} {'WR%':>6s} {'avg%':>7s} {'med%':>7s} "
          f"{'PF':>5s} {'stop%':>6s} {'cat%':>5s} {'worst%':>7s} {'days':>5s}")
    for pol in POLICIES:
        m = res["by_policy"].get(pol, {})
        if not m.get("n"): continue
        print(f"  {pol:14s} {m['n']:4d} {m['wr_pct']:6.2f} "
              f"{m['avg_pct']:+7.3f} {m['median_pct']:+7.3f} "
              f"{str(m['profit_factor']):>5s} {m['stop_hit_rate_pct']:6.2f} "
              f"{m['catastrophic_gt10pct_pct']:5.2f} {m['worst_pct']:+7.3f} "
              f"{str(m['avg_days_held']):>5s}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = run_market(root, m)
        p = emit(root, m, res)
        render_console(res)
        print(f"\n[stop_sweep:{m}] -> {p.name if p else 'none'}")

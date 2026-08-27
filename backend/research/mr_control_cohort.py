"""AEGIS · M-R2 · Control Cohort Baseline · Sprint M.

For each historical prediction day, sample the ENTIRE parquet universe
uniformly and compute the same fwd_5d/fwd_10d distribution AEGIS is being
scored against. This is the null-hypothesis baseline: what would a random
buy-anything strategy have delivered on the same days?

If AEGIS WR / avg is not meaningfully above this baseline, AEGIS is not
adding predictive value on that horizon.

Emits reports/research/mr_control_cohort_{market}.json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_control_cohort.v0.1"


def _universe_paths(root: Path, market: str) -> list:
    base = root / ("usa/data/raw/us" if market.lower()=="usa" else "data/raw/india")
    return sorted(base.glob("*_D1.parquet")) if base.exists() else []


def _fwd(df, col, iso: str, horizon: int) -> Optional[float]:
    dates = sorted(df.index)
    if iso in df.index:
        i = dates.index(iso)
    else:
        earlier = [d for d in dates if d <= iso]
        if not earlier: return None
        i = dates.index(earlier[-1])
    fi = i + horizon
    if fi >= len(dates): return None
    try:
        p0 = float(df.loc[dates[i], col])
        p1 = float(df.loc[dates[fi], col])
        if p0 <= 0: return None
        return round((p1 - p0)/p0*100, 3)
    except Exception:
        return None


def _load_days(root: Path, market: str) -> set:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return set()
    days = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try: days.add(json.loads(ln).get("prediction_date"))
        except Exception: continue
    return {d for d in days if d}


def run_market(root: Path, market: str) -> dict:
    import pandas as pd
    days = sorted(_load_days(root, market))
    if not days: return {}
    universe = _universe_paths(root, market)
    price_cache: dict = {}
    for pth in universe:
        try:
            df = pd.read_parquet(pth)
            col = "close" if "close" in df.columns else "Close"
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            price_cache[pth.stem.replace("_D1","")] = (df, col)
        except Exception:
            continue

    def _agg(rets: list) -> dict:
        if not rets: return {"n":0}
        wins = sum(1 for v in rets if v > 0.5)
        return {
            "n":         len(rets),
            "wr_pct":    round(wins/len(rets)*100, 2),
            "avg_pct":   round(mean(rets), 3),
            "median_pct":round(median(rets), 3),
            "best_pct":  round(max(rets), 3),
            "worst_pct": round(min(rets), 3),
        }

    fwd_5d = []; fwd_10d = []; fwd_20d = []
    per_day: dict = {}
    for d in days:
        day_5 = []; day_10 = []; day_20 = []
        for tk, (df, col) in price_cache.items():
            f5 = _fwd(df, col, d, 5)
            f10 = _fwd(df, col, d, 10)
            f20 = _fwd(df, col, d, 20)
            if f5 is not None: day_5.append(f5); fwd_5d.append(f5)
            if f10 is not None: day_10.append(f10); fwd_10d.append(f10)
            if f20 is not None: day_20.append(f20); fwd_20d.append(f20)
        per_day[d] = {
            "fwd_5d": _agg(day_5),
            "fwd_10d": _agg(day_10),
        }
    return {
        "engine":         ENGINE_ID,
        "experiment_id":  EXPERIMENT_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":         market.upper(),
        "universe_size":  len(price_cache),
        "n_days":         len(days),
        "aggregate": {
            "fwd_5d":  _agg(fwd_5d),
            "fwd_10d": _agg(fwd_10d),
            "fwd_20d": _agg(fwd_20d),
        },
        "per_day":        per_day,
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_control_cohort_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res: return
    print(f"\n======== CONTROL COHORT · {res['market']} ========")
    print(f"  universe_size = {res['universe_size']} · n_days = {res['n_days']}")
    for hz in ("fwd_5d","fwd_10d","fwd_20d"):
        a = res["aggregate"][hz]
        if a.get("n"):
            print(f"  {hz}: n={a['n']} · WR={a['wr_pct']}% · avg={a['avg_pct']:+}% · "
                  f"median={a['median_pct']:+}% · worst={a['worst_pct']} · best={a['best_pct']}")


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
        print(f"\n[control_cohort:{m}] -> {p.name}")

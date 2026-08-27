"""AEGIS · M-R · Missed Winners · Sprint M Phase C.

Answers "what did AEGIS MISS?" (false negatives).

For each historical prediction day, scan the full ticker universe (all
parquets in data/raw/india + usa/data/raw/us), compute fwd_5d and fwd_10d,
identify winners > +5% and > +10% that AEGIS did NOT recommend that day.

Emits:
  reports/research/mr_missed_winners_{market}.json  (per-day + aggregate)

Under M-R sandbox rules. No production side effects.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_missed_winners.v0.1"


def _universe_paths(root: Path, market: str) -> list:
    base = root / ("usa/data/raw/us" if market.lower()=="usa" else "data/raw/india")
    if not base.exists(): return []
    return sorted(base.glob("*_D1.parquet"))


def _fwd_5d(df, col, iso: str, horizon: int = 5) -> Optional[float]:
    dates = sorted(df.index)
    if iso not in df.index:
        earlier = [d for d in dates if d <= iso]
        if not earlier: return None
        i = dates.index(earlier[-1])
    else:
        i = dates.index(iso)
    fi = i + horizon
    if fi >= len(dates): return None
    try:
        p0 = float(df.loc[dates[i], col])
        p1 = float(df.loc[dates[fi], col])
        if p0 <= 0: return None
        return round((p1 - p0)/p0*100, 3)
    except Exception:
        return None


def _load_predictions(root: Path, market: str) -> dict:
    """Return {prediction_date: set(tickers)} for what AEGIS actually recommended."""
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return {}
    by_date: defaultdict = defaultdict(set)
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try: r = json.loads(ln)
        except Exception: continue
        dt = r.get("prediction_date")
        tk = r.get("ticker")
        if dt and tk:
            by_date[dt].add(tk.upper())
    return dict(by_date)


def run_market(root: Path, market: str) -> dict:
    import pandas as pd
    predicted = _load_predictions(root, market)
    if not predicted:
        return {"engine": ENGINE_ID, "market": market.upper(),
                "status": "NO_PREDICTIONS_FOUND"}
    days = sorted(predicted.keys())
    universe = _universe_paths(root, market)
    # Preload all parquets (memory ok — <300 tickers each market)
    price_cache: dict = {}
    for pth in universe:
        tk = pth.stem.replace("_D1","").upper()
        try:
            df = pd.read_parquet(pth)
            col = "close" if "close" in df.columns else "Close"
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            price_cache[tk] = (df, col)
        except Exception:
            continue

    missed = defaultdict(list)   # date -> [(ticker, fwd_5d)]
    caught = defaultdict(list)
    for dt in days:
        rec = predicted[dt]
        for tk, (df, col) in price_cache.items():
            f5 = _fwd_5d(df, col, dt, 5)
            if f5 is None: continue
            if f5 >= 5.0:  # big winner threshold
                if tk in rec:
                    caught[dt].append((tk, f5))
                else:
                    missed[dt].append((tk, f5))

    # Aggregate
    total_recommended = sum(len(v) for v in predicted.values())
    total_big_winners_missed = sum(len(v) for v in missed.values())
    total_big_winners_caught = sum(len(v) for v in caught.values())
    # Sector concentration on missed
    per_day_stats = []
    for dt in days:
        m = missed.get(dt, [])
        c = caught.get(dt, [])
        per_day_stats.append({
            "date": dt,
            "n_recommended": len(predicted[dt]),
            "n_big_winners_caught": len(c),
            "n_big_winners_missed": len(m),
            "top_missed": sorted(m, key=lambda x: -x[1])[:10],
        })

    return {
        "engine":            ENGINE_ID,
        "market":            market.upper(),
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe_size":     len(price_cache),
        "n_days":            len(days),
        "n_recommended_total":       total_recommended,
        "n_big_winners_caught_ge5pct": total_big_winners_caught,
        "n_big_winners_missed_ge5pct": total_big_winners_missed,
        "capture_rate_pct":  round(total_big_winners_caught /
                                    max(1, total_big_winners_caught + total_big_winners_missed) * 100, 2),
        "avg_missed_per_day": round(total_big_winners_missed / max(1, len(days)), 2),
        "per_day":           per_day_stats,
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_missed_winners_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res or res.get("status") == "NO_PREDICTIONS_FOUND": return
    print(f"\n======== MISSED WINNERS · {res['market']} ========")
    print(f"  universe_size = {res['universe_size']}")
    print(f"  n_days        = {res['n_days']}")
    print(f"  total_recommended = {res['n_recommended_total']}")
    print(f"  big winners >=5% CAUGHT  = {res['n_big_winners_caught_ge5pct']}")
    print(f"  big winners >=5% MISSED  = {res['n_big_winners_missed_ge5pct']}")
    print(f"  capture_rate = {res['capture_rate_pct']}%")
    print(f"  avg_missed_per_day = {res['avg_missed_per_day']}")
    print(f"\n  Top 10 sample days (by n_missed):")
    top = sorted(res["per_day"], key=lambda d: -d["n_big_winners_missed"])[:10]
    for d in top:
        tk_sample = ", ".join(f"{t}({p:+.1f}%)" for t, p in d["top_missed"][:3])
        print(f"    {d['date']} · rec={d['n_recommended']} · "
              f"caught={d['n_big_winners_caught']} · missed={d['n_big_winners_missed']} · "
              f"top={tk_sample}")


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
        print(f"\n[missed:{m}] -> {p.name}")

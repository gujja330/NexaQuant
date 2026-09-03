"""V2 Phase H · Paper Comparator · daily tick recorder.

Records one JSONL line per (market, date) with:
  r2_production_picks_today  (rank-1 through rank-N from recs_v3)
  standing_comparator_picks  (top-10 3-mo momentum · equal-weight)
  candidate_strategy_picks   (empty until a research strategy is declared)

Append-only. Never rewritten. Substrate for sustained-evidence forward gate.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path


def _load_r2_today(root: Path, market: str) -> list[dict]:
    p = ((root / "usa" / "reports" / "recommendations_v3.json") if market == "usa"
         else (root / "reports" / "recommendations_v3.json"))
    if not p.exists(): return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    picks = []
    for r in (d.get("recommendations") or []):
        picks.append({
            "ticker": str(r.get("ticker","")).upper().split(".",1)[0],
            "rank": r.get("rank"),
            "action": str(r.get("action","")).upper(),
            "ensemble_score": r.get("ensemble_score"),
            "calibrated_confidence": r.get("calibrated_confidence"),
        })
    return picks


def _standing_comparator_picks(root: Path, market: str, asof: str,
                               top_n: int = 10) -> list[dict]:
    """Equal-weight top-10 by 3-month momentum · permanent · never optimized."""
    import pandas as pd
    from backend.research._paths import price_parquet_dir, price_parquet_path

    # Universe from PIT if available · else fall back to all tickers with parquet
    universe: list[str] = []
    if market == "usa":
        u_path = root / "usa" / "reports" / "universe.json"
    else:
        u_path = root / "reports" / "india_universe.json"
    if u_path.exists():
        try:
            d = json.loads(u_path.read_text(encoding="utf-8"))
            if isinstance(d, list):
                for x in d:
                    if isinstance(x, str): universe.append(x.upper())
                    elif isinstance(x, dict):
                        for k in ("SYMBOL","symbol","TICKER","ticker"):
                            if k in x: universe.append(str(x[k]).upper()); break
            elif isinstance(d, dict):
                for k in ("tickers","constituents","members"):
                    if k in d and isinstance(d[k], list):
                        for x in d[k]:
                            if isinstance(x, str): universe.append(x.upper())
                            elif isinstance(x, dict):
                                for kk in ("SYMBOL","symbol","TICKER","ticker"):
                                    if kk in x: universe.append(str(x[kk]).upper()); break
        except Exception:
            pass
    if not universe:
        d = price_parquet_dir(root, market)
        if d.exists():
            for f in d.glob("*_D1.parquet"):
                universe.append(f.stem.replace("_D1", "").upper())

    asof_dt = pd.to_datetime(asof).normalize()
    lookback = asof_dt - pd.DateOffset(months=3)

    momos = []
    for t in universe:
        p = price_parquet_path(root, market, t)
        if not p or not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            past = df[df.index <= lookback].tail(1)
            now = df[df.index <= asof_dt].tail(1)
            if past.empty or now.empty: continue
            r = (float(now["close"].iloc[-1]) / float(past["close"].iloc[-1])) - 1.0
            momos.append({"ticker": t, "mom_3mo": round(r, 6)})
        except Exception:
            continue
    momos.sort(key=lambda x: -x["mom_3mo"])
    return momos[:top_n]


def record_daily_tick(root: Path, market: str,
                      asof: str | None = None,
                      candidate_picks: list[dict] | None = None) -> dict:
    """Append one day's paper-comparator tick."""
    asof = asof or datetime.now().strftime("%Y-%m-%d")
    payload = {
        "asof": asof,
        "market": market,
        "r2_production_picks": _load_r2_today(root, market),
        "standing_comparator_picks_top10_3mo_mom": _standing_comparator_picks(root, market, asof, top_n=10),
        "candidate_strategy_picks": candidate_picks or [],
        "recorded_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "governance_note": (
            "Paper comparator · read-only tracking · never production. "
            "Sustained forward evidence required before any candidate strategy "
            "is considered for controlled promotion."
        ),
    }
    out_dir = root / "reports" / "research" / "paper_comparator"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = out_dir / f"{market}.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")
    (out_dir / f"latest_{market}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return payload


def main():
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = record_daily_tick(root, m, args.asof)
        print(f"[paper-comparator] {m} · asof={r['asof']} · r2_picks={len(r['r2_production_picks'])} · std_comp_picks={len(r['standing_comparator_picks_top10_3mo_mom'])}")


if __name__ == "__main__":
    main()

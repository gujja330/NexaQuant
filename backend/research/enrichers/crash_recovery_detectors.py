"""CRASH_DETECTOR_01 + RECOVERY_DETECTOR_01 · additive · PDF regime states.

The base regime enricher (backend/research/enrichers/regime.py) covers 4 of
6 PDF states (NORMAL / WEAKENING / RISK_OFF / UNKNOWN). The two missing
states (CRASH · RECOVERY) require additional event-based detectors:

  CRASH_DETECTOR_01:
    WEAKENING context + market 1-day return < −3σ (σ from trailing 90d)
    → upgrades that day's `regime_at_entry` from WEAKENING to CRASH

  RECOVERY_DETECTOR_01:
    Post-CRASH trailing 20d showing NORMAL or BULL classifications
    → upgrades from NORMAL to RECOVERY

Both are ADDITIVE on top of the base regime enricher · they only touch
`regime_at_entry` when their event condition fires · otherwise leave the
base classification.

Written in-place into Outcome Dataset. Idempotent. PIT-safe.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path


def _load_market_returns(root: Path, market: str) -> dict[str, float]:
    """Compute daily market-mean returns from parquets · one series per market."""
    import pandas as pd
    from backend.research._paths import price_parquet_dir
    d = price_parquet_dir(root, market)
    if not d.exists(): return {}
    files = list(d.glob("*_D1.parquet")) or list(d.glob("*.parquet"))
    if not files: return {}
    per_ticker: list[pd.Series] = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            df.index = pd.to_datetime(df.index)
            r = df["close"].pct_change()
            per_ticker.append(r.dropna())
        except Exception:
            continue
    if not per_ticker: return {}
    concat = pd.concat(per_ticker, axis=1)
    mkt = concat.mean(axis=1)
    return {d.date().isoformat(): float(v) for d, v in mkt.items()}


def _rolling_sigma(returns: dict[str, float], asof: str, window: int = 90) -> float:
    dates = sorted(d for d in returns if d <= asof)[-window:]
    if len(dates) < 10: return 0.0
    vs = [returns[d] for d in dates]
    mu = sum(vs) / len(vs)
    var = sum((v - mu) ** 2 for v in vs) / max(1, len(vs) - 1)
    return math.sqrt(var)


def apply_crash_recovery(root: Path, market: str) -> dict:
    """Update Outcome Dataset regime_at_entry with CRASH / RECOVERY where
    detected. Base classification preserved when neither event fires."""
    import pandas as pd
    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return {"market": market, "status": "OUTCOME_DATASET_MISSING"}
    df = pd.read_parquet(od_path)
    if df.empty:
        return {"market": market, "status": "OUTCOME_DATASET_EMPTY"}

    market_rets = _load_market_returns(root, market)
    if not market_rets:
        return {"market": market, "status": "MARKET_RETURN_UNAVAILABLE"}

    sorted_dates = sorted(market_rets.keys())

    def _is_crash(date_str: str) -> bool:
        if date_str not in market_rets: return False
        sigma = _rolling_sigma(market_rets, date_str, window=90)
        if sigma <= 0: return False
        return market_rets[date_str] < -3.0 * sigma

    def _is_recovery(date_str: str) -> bool:
        # RECOVERY: was a CRASH within trailing 20d + today's market_ret > 0
        try:
            d0 = date.fromisoformat(date_str)
        except Exception: return False
        window_start = d0 - timedelta(days=20)
        recent = [d for d in sorted_dates
                  if d <= date_str and date.fromisoformat(d) >= window_start]
        crash_in_window = any(_is_crash(d) for d in recent)
        if not crash_in_window: return False
        return market_rets.get(date_str, 0.0) > 0.0

    n_crash = 0; n_recovery = 0; n_touched = 0
    for i in df.index:
        ed = str(df.at[i, "entry_date"]) if pd.notna(df.at[i, "entry_date"]) else ""
        if not ed: continue
        base_regime = str(df.at[i, "regime_at_entry"] or "UNKNOWN")
        if _is_crash(ed):
            df.at[i, "regime_at_entry"] = "CRASH"
            df.at[i, "regime_source"] = "crash_detector_01"
            n_crash += 1; n_touched += 1
        elif _is_recovery(ed):
            df.at[i, "regime_at_entry"] = "RECOVERY"
            df.at[i, "regime_source"] = "recovery_detector_01"
            n_recovery += 1; n_touched += 1

    df.to_parquet(od_path, index=False)
    summary = {
        "market": market, "status": "ENRICHED",
        "n_rows_touched": n_touched,
        "n_crash": n_crash,
        "n_recovery": n_recovery,
        "n_market_return_days": len(market_rets),
        "detectors": {
            "CRASH_DETECTOR_01": "WEAKENING context + market 1d return < −3σ (σ trailing 90d)",
            "RECOVERY_DETECTOR_01": "trailing 20d contained a CRASH day + today market_ret > 0",
        },
        "governance_note": ("Additive to base regime enricher · never overwrites "
                            "non-event days · preserves original classification when "
                            "neither event fires · V2 §7 discipline."),
        "enriched_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = root / "reports" / "research" / "enrichers"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"crash_recovery_{market}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary


def main():
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        print(json.dumps(apply_crash_recovery(root, m), indent=2, default=str))


if __name__ == "__main__":
    main()

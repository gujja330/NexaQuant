"""Auto-accumulate fundamentals daily · snapshot per asof · PIT-ready builder.

CEO 2026-09-03 · turn Deep Research into continuously-advancing evidence program.
This script runs daily and appends today's fundamentals snapshot with asof stamp.
Historical PIT store grows over time · enables real walk-forward research
for Fundamental Intelligence (D01-D05) instead of single-day cross-sections.

Usage (cron this daily):
    python scripts/accumulate_fundamentals_history.py --market both

Output:
    reports/research/fundamentals_history/{market}.parquet   (append-only · dedupe by ticker+asof)
"""
from __future__ import annotations
import argparse, io, json, sys
from datetime import datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass


def append_snapshot(root: Path, market: str) -> dict:
    """Append today's FS snapshot to the historical accumulator."""
    import pandas as pd
    today_path = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not today_path.exists():
        return {"market": market, "status": "NO_TODAY_SNAPSHOT",
                "hint": "run populate_fundamentals_feature_store first"}
    today = pd.read_parquet(today_path)
    if today.empty:
        return {"market": market, "status": "EMPTY_SNAPSHOT"}

    hist_dir = root / "reports" / "research" / "fundamentals_history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist_path = hist_dir / f"{market}.parquet"

    if hist_path.exists():
        try:
            hist = pd.read_parquet(hist_path)
            combined = pd.concat([hist, today], ignore_index=True)
        except Exception:
            combined = today
    else:
        combined = today

    # Dedupe by ticker + asof · last-write wins
    combined = combined.drop_duplicates(subset=["market", "ticker", "asof"], keep="last")
    combined = combined.sort_values(["ticker", "asof"]).reset_index(drop=True)
    combined.to_parquet(hist_path, index=False)

    # Summary
    n_tickers = combined["ticker"].nunique()
    n_asof = combined["asof"].nunique()
    n_rows = len(combined)
    return {
        "market": market,
        "status": "APPENDED",
        "n_rows_total": int(n_rows),
        "n_unique_tickers": int(n_tickers),
        "n_unique_asof_dates": int(n_asof),
        "hist_path": str(hist_path.relative_to(root)),
        "note": (
            f"Historical PIT store has {n_asof} distinct asof dates · "
            "grows daily · unblocks Fundamental Intelligence walk-forward research"
        ),
        "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = append_snapshot(_ROOT, m)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()

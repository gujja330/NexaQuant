"""Momentum forward-outcomes measurement · CEO 2026-09-01.

For each historical momentum-ledger snapshot (`reports/research/
momentum_snapshots/{market}_{asof}.jsonl`), when today's date is
≥ (snapshot_date + n trading days), compute the realized forward
return over that window and update the snapshot's forward_outcomes.

Measurement only · never modifies R2 · never auto-promotes. Windows:
    d1 · d3 · d5 · d10 · d20 (trading days)

Reads price data from `data/raw/{TICKER}[.NS]_D1.parquet`.
Writes updated snapshots back in place · idempotent.

Skips a candidate when historical data is insufficient for a window ·
records `UNAVAILABLE` in that slot rather than a fabricated value.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

WINDOWS = [("d1", 1), ("d3", 3), ("d5", 5), ("d10", 10), ("d20", 20)]


def _load_closes(root: Path, ticker: str, market: str):
    """Return list of (date, close) sorted ascending · or None."""
    suffix = ".NS" if market.lower() == "india" else ""
    candidates = [
        root / "data" / "raw" / f"{ticker.upper()}{suffix}_D1.parquet",
        root / "data" / "raw" / f"{ticker.upper()}_D1.parquet",
    ]
    parq = next((p for p in candidates if p.exists()), None)
    if parq is None:
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(parq)
    except Exception:
        return None
    if "close" not in df.columns and "Close" in df.columns:
        df = df.rename(columns={"Close": "close"})
    if "close" not in df.columns:
        return None
    df = df.dropna(subset=["close"])
    df.index = df.index.astype(str)
    return sorted([(d[:10], float(c)) for d, c in df["close"].items()])


def _forward_return_pct(closes, from_date: str, n_trading_days: int):
    """Return pct return from close on the trading day at/after from_date
    to the close n trading days later. UNAVAILABLE if insufficient data."""
    idx = None
    for i, (d, _) in enumerate(closes):
        if d >= from_date:
            idx = i
            break
    if idx is None: return "UNAVAILABLE"
    base = closes[idx][1]
    target = idx + n_trading_days
    if target >= len(closes): return "UNAVAILABLE"
    if base <= 0: return "UNAVAILABLE"
    return round((closes[target][1] - base) / base * 100, 3)


def measure(root: Path, market: str, asof: str) -> dict:
    snap_dir = root / "reports" / "research" / "momentum_snapshots"
    if not snap_dir.exists():
        return {"error": "no snapshots directory yet", "market": market}
    files = sorted(snap_dir.glob(f"{market.lower()}_*.jsonl"))
    today_d = date.fromisoformat(asof)
    n_updated = 0
    n_snapshots = 0
    for f in files:
        # Extract snapshot date from filename
        try:
            snap_date_str = f.stem.split("_")[-1]
            snap_date = date.fromisoformat(snap_date_str)
        except Exception:
            continue
        n_snapshots += 1
        # Days elapsed since snapshot
        elapsed = (today_d - snap_date).days
        if elapsed < 1: continue

        # Load + update
        entries = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        changed_any = False
        for e in entries:
            fo = e.get("forward_outcomes") or {}
            for key, n in WINDOWS:
                if elapsed < n: continue
                # Only measure if not yet measured (NOT_MEASURED_YET)
                if str(fo.get(key, "")) == "NOT_MEASURED_YET":
                    closes = _load_closes(root, e["ticker"], market)
                    if closes is None:
                        fo[key] = "UNAVAILABLE"
                    else:
                        fo[key] = _forward_return_pct(closes, snap_date_str, n)
                    changed_any = True
            e["forward_outcomes"] = fo
        if changed_any:
            with f.open("w", encoding="utf-8") as fh:
                for e in entries:
                    fh.write(json.dumps(e, ensure_ascii=False,
                                          default=str) + "\n")
            n_updated += 1
    return {
        "market": market.lower(),
        "asof": asof,
        "n_snapshots_scanned": n_snapshots,
        "n_snapshots_updated": n_updated,
        "windows": [k for k, _ in WINDOWS],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                     default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = measure(_ROOT, m, args.asof)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

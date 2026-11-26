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
from datetime import date
from math import isfinite
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backend.shared.atomic_io import write_text_atomic

WINDOWS = [("d1", 1), ("d3", 3), ("d5", 5), ("d10", 10), ("d20", 20)]


def _load_closes(root: Path, ticker: str, market: str):
    """Return list of (date, close) sorted ascending · or None."""
    from backend.research._paths import price_parquet_path

    symbol = ticker.upper().removesuffix(".NS").removesuffix(".BO")
    parq = price_parquet_path(root, market, symbol)
    if parq is None:
        suffix = ".NS" if market.lower() == "india" else ""
        candidates = [
            root / "data" / "raw" / f"{symbol}{suffix}_D1.parquet",
            root / "data" / "raw" / f"{symbol}_D1.parquet",
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
    if not isfinite(base) or base <= 0 or not isfinite(closes[target][1]):
        return "UNAVAILABLE"
    return round((closes[target][1] - base) / base * 100, 3)


def measure(root: Path, market: str, asof: str) -> dict:
    snap_dir = root / "reports" / "research" / "momentum_snapshots"
    if not snap_dir.exists():
        return {"asof": asof, "status": "NO_SNAPSHOTS", "market": market}
    files = sorted(snap_dir.glob(f"{market.lower()}_*.jsonl"))
    today_d = date.fromisoformat(asof)
    n_updated = 0
    n_snapshots = 0
    resolved = 0
    malformed_snapshots = []
    closes_by_ticker = {}
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
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    if not isinstance(entry, dict) or not entry.get("ticker"):
                        raise ValueError("snapshot row has no ticker")
                    entries.append(entry)
        except ValueError:
            malformed_snapshots.append(f.name)
            continue
        changed_any = False
        for e in entries:
            fo = e.get("forward_outcomes") or {}
            for key, n in WINDOWS:
                if elapsed < n: continue
                if fo.get(key) not in (None, "NOT_MEASURED_YET", "UNAVAILABLE"):
                    continue
                ticker = e["ticker"]
                if ticker not in closes_by_ticker:
                    closes = _load_closes(root, ticker, market) or []
                    closes_by_ticker[ticker] = [(day, price) for day, price in closes if day <= asof]
                value = _forward_return_pct(closes_by_ticker[ticker], snap_date_str, n)
                if isinstance(value, (int, float)):
                    fo[key] = value
                    changed_any = True
                    resolved += 1
            e["forward_outcomes"] = fo
        if changed_any:
            temp = f.with_suffix(".tmp")
            try:
                with temp.open("w", encoding="utf-8") as handle:
                    for entry in entries:
                        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
                temp.replace(f)
            finally:
                temp.unlink(missing_ok=True)
            n_updated += 1
    return {
        "market": market.lower(),
        "asof": asof,
        "n_snapshots_scanned": n_snapshots,
        "n_snapshots_updated": n_updated,
        "n_horizons_resolved": resolved,
        "malformed_snapshots": malformed_snapshots,
        "windows": [k for k, _ in WINDOWS],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                     default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    failed = False
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = measure(_ROOT, m, args.asof)
        payload = json.dumps(rep, indent=2, ensure_ascii=False)
        receipt = _ROOT / "reports" / "research" / "momentum_snapshots" / f"receipt_{m}_{args.asof}.json"
        write_text_atomic(receipt, payload)
        print(payload)
        failed |= bool(rep.get("malformed_snapshots"))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())

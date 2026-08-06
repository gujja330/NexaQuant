"""Rebuild position_store first_seen_price / high_water / low_water using
authoritative bar data (parquet close on first_seen_date).

Operator P0 audit 2026-08-06: position_store first_seen_price is
corrupted (captured pre-market or on wrong date). This script re-anchors
every position's Entry Price to the actual bar close on its first_seen_date.

Idempotent · safe to re-run.
"""
from __future__ import annotations

import json, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load_bar(market: str, ticker: str):
    import pandas as pd
    short = ticker.replace(".NS", "").replace(".BO", "")
    d = _ROOT / ("usa/data/raw/us" if market == "usa" else "data/raw/india")
    p = d / f"{short}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df
    except Exception:
        return None


def _bar_close(df, date_str: str):
    if df is None: return None
    if date_str in df.index:
        return float(df.loc[date_str, "close"])
    earlier = [d for d in df.index if d <= date_str]
    if earlier:
        return float(df.loc[earlier[-1], "close"])
    return None


def rebuild(market: str) -> dict:
    reports = _ROOT / ("usa/reports" if market == "usa" else "reports")
    p = reports / "position_store" / market / "positions.json"
    if not p.exists(): return {"error": f"{p} missing"}
    d = json.loads(p.read_text(encoding="utf-8"))
    positions = d.get("positions") or {}
    fixed = 0
    unchanged = 0
    for tk, pos in positions.items():
        first_seen = str(pos.get("first_seen_date") or "")[:10]
        if not first_seen: continue
        df = _load_bar(market, tk)
        entry_from_bar = _bar_close(df, first_seen)
        if entry_from_bar is None: continue
        old_entry = pos.get("first_seen_price")
        if old_entry and abs(old_entry - entry_from_bar) < 0.01:
            unchanged += 1
            continue
        # Also fix high/low water from bars in range [first_seen, last_seen]
        last_seen = str(pos.get("last_seen_date") or "")[:10]
        if last_seen and df is not None:
            window = df[(df.index >= first_seen) & (df.index <= last_seen)]
            if not window.empty:
                pos["high_water_price"] = round(float(window["close"].max()), 2)
                pos["low_water_price"] = round(float(window["close"].min()), 2)
                pos["last_seen_price"] = round(float(window["close"].iloc[-1]), 2)
        pos["first_seen_price"] = round(entry_from_bar, 2)
        pos["_price_source_fix"] = "rebuilt from bar close on first_seen_date"
        fixed += 1
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"fixed": fixed, "unchanged": unchanged, "total": len(positions),
                "market": market, "path": str(p)}


def main() -> int:
    import io
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    for m in ("india", "usa"):
        r = rebuild(m)
        if "error" in r:
            print(f"[{m}] {r['error']}"); continue
        print(f"[{m}] rebuilt {r['fixed']}/{r['total']} positions (unchanged {r['unchanged']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

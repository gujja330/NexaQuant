"""AEGIS · R3 · OUTCOME ACCUMULATOR · the R3 evidence clock.

CEO 2026-09-07 · R3 Sprint 1 item 9. Every R3 shadow pick enters once at
T0 and is measured forward at 5 / 10 / 20 / 60 **trading** days.

    T0 ─5td─> fwd_5d ─10td─> fwd_10d ─20td─> fwd_20d ─60td─> fwd_60d

TWO RULES THAT MAKE THIS EVIDENCE RATHER THAN A NUMBER
------------------------------------------------------
1. AS-OF AWARE. A horizon is filled only once it has actually closed on
   the trading calendar. Before that it stays `PENDING`. No future outcome
   is ever visible early · that would be the same lookahead the audit
   caught in the feature store, just moved to the label side.

2. TRADING DAYS, NOT CALENDAR DAYS. "5 days" after a Friday is the
   following Friday, not the following Wednesday. Horizons are counted on
   the market's own price index, so weekends and holidays cannot silently
   shorten a horizon.

Idempotent: re-running fills only horizons that are still PENDING and have
closed. An already-measured horizon is never rewritten, so a later data
revision cannot quietly restate published evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.research.r3.ledger_schema import (
    HORIZONS, NOT_AVAILABLE, PENDING, SCHEMA_VERSION, is_canonical, migrate,
)


def _price_series(root: Path, market: str, ticker: str):
    """Ascending (date, close) for a ticker · None when unreadable."""
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists():
            return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        col = "close" if "close" in df.columns else "Close"
        if col not in df.columns:
            return None
        return df[[col]].rename(columns={col: "close"}), df
    except Exception:
        return None


def _bars_after(df, asof: str):
    """Rows strictly AFTER asof · the forward window."""
    import pandas as pd
    t = pd.to_datetime(asof).normalize()
    return df[df.index > t]


def measure(root: Path, market: str, ticker: str, asof: str,
            entry_price: Optional[float], today: str) -> dict:
    """Return the outcome block updates that are legitimately knowable.

    Only horizons whose bar count has been reached AND whose closing date
    is on/before `today` are filled.
    """
    res = {}
    loaded = _price_series(root, market, ticker)
    if loaded is None:
        # Unreadable price data · say so rather than emitting 0.0.
        for h in HORIZONS:
            res[f"fwd_{h}d_return_pct"] = NOT_AVAILABLE
            res[f"fwd_{h}d_closed_on"] = NOT_AVAILABLE
        return res
    closes, full = loaded
    fwd = _bars_after(closes, asof)
    if fwd.empty:
        return res  # nothing has traded since T0 · leave everything PENDING

    import pandas as pd
    today_ts = pd.to_datetime(today).normalize()

    # Baseline is the T0 close when no explicit entry was recorded.
    base = entry_price
    if not base:
        at_or_before = closes[closes.index <= pd.to_datetime(asof).normalize()]
        if at_or_before.empty:
            return res
        base = float(at_or_before["close"].iloc[-1])
    if not base or base <= 0:
        return res

    for h in HORIZONS:
        if len(fwd) < h:
            continue                      # horizon has not closed · PENDING
        bar = fwd.iloc[h - 1]
        closed_on = fwd.index[h - 1]
        if closed_on > today_ts:
            continue                      # cannot be knowable yet
        res[f"fwd_{h}d_return_pct"] = round(
            (float(bar["close"]) / base - 1.0) * 100, 4)
        res[f"fwd_{h}d_closed_on"] = closed_on.date().isoformat()

    # MAE / MFE over the longest CLOSED horizon only · an excursion measured
    # over a window that has not finished would move as the window grows.
    closed = [h for h in HORIZONS
              if isinstance(res.get(f"fwd_{h}d_return_pct"), (int, float))]
    if closed:
        h = max(closed)
        window = fwd.iloc[:h]
        try:
            hi = full.loc[window.index, "high"] if "high" in full.columns else window["close"]
            lo = full.loc[window.index, "low"] if "low" in full.columns else window["close"]
            res["mfe_pct"] = round((float(hi.max()) / base - 1.0) * 100, 4)
            res["mae_pct"] = round((float(lo.min()) / base - 1.0) * 100, 4)
        except Exception:
            res["mfe_pct"] = round((float(window["close"].max()) / base - 1.0) * 100, 4)
            res["mae_pct"] = round((float(window["close"].min()) / base - 1.0) * 100, 4)
        res["pnl_pct"] = res[f"fwd_{h}d_return_pct"]
    return res


def accumulate(root: Path, today: str, market: Optional[str] = None) -> dict:
    """Fill every closed-but-unmeasured horizon in the canonical ledger.

    Returns a summary. Never rewrites a horizon that already holds a real
    measurement.
    """
    from backend.research.r3 import shadow_ledger as sl

    p = sl._ledger_path(root)
    if not p.exists():
        return {"status": "NO_LEDGER", "path": str(p)}

    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    n_filled = 0
    n_rows_touched = 0
    n_pending = 0
    for rec in rows:
        if not is_canonical(rec):
            continue
        if market and rec.get("market") != market.lower():
            continue
        out = rec.get("outcome") or {}
        # Which horizons are still open?
        open_h = [h for h in HORIZONS
                  if out.get(f"fwd_{h}d_return_pct") == PENDING]
        if not open_h:
            continue
        upd = measure(root, rec.get("market"), rec.get("ticker"),
                      rec.get("asof"),
                      (rec.get("risk") or {}).get("entry_price"), today)
        touched = False
        for k, v in upd.items():
            # Only fill a slot that is still PENDING · never restate.
            if out.get(k) == PENDING:
                out[k] = v
                touched = True
                if k.endswith("_return_pct"):
                    n_filled += 1
        if touched:
            out["outcome_last_updated"] = today
            rec["outcome"] = out
            n_rows_touched += 1
        n_pending += sum(1 for h in HORIZONS
                         if out.get(f"fwd_{h}d_return_pct") == PENDING)

    p.write_text("".join(json.dumps(r, default=str, ensure_ascii=False) + "\n"
                         for r in rows), encoding="utf-8")
    return {
        "status": "OK",
        "today": today,
        "n_records": len(rows),
        "n_rows_updated": n_rows_touched,
        "n_horizons_filled": n_filled,
        "n_horizons_still_pending": n_pending,
        "path": str(p.relative_to(root)),
    }


def migrate_ledger(root: Path) -> dict:
    """Lift every legacy row in the canonical ledger to schema v2."""
    from backend.research.r3 import shadow_ledger as sl

    p = sl._ledger_path(root)
    if not p.exists():
        return {"status": "NO_LEDGER"}
    rows, n_mig = [], 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not is_canonical(rec):
            rec = migrate(rec)
            n_mig += 1
        rows.append(rec)
    p.write_text("".join(json.dumps(r, default=str, ensure_ascii=False) + "\n"
                         for r in rows), encoding="utf-8")
    return {"status": "OK", "n_records": len(rows), "n_migrated": n_mig,
            "schema_version": SCHEMA_VERSION}


def main() -> int:
    import argparse
    from datetime import date

    ap = argparse.ArgumentParser(description="R3 outcome accumulator")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--root", default=None)
    ap.add_argument("--migrate", action="store_true",
                    help="lift legacy rows to the canonical schema first")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]

    if a.migrate:
        print(json.dumps(migrate_ledger(root), indent=2))
    markets = [None] if a.market == "both" else [a.market]
    for m in markets:
        print(json.dumps(accumulate(root, a.today, m), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

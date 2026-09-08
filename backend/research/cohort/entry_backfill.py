"""USA ENTRY-PRICE BACKFILL · R3-G Wave 1A · CEO 2026-09-08.

> "Backfill USA entry prices PIT-safely from historical bars. Do not
>  fabricate stops for never-opened candidates."

WHAT IS AND IS NOT RECONSTRUCTABLE
-----------------------------------
These are not the same kind of fact and must not be treated alike:

  entry_price  an OBSERVABLE market value on the prediction date. The bar
               existed; the workbook simply failed to write the column.
               USA R2 coverage is 8.2% while the resolver returns a price
               for every ticker tested (CPAY 406.16, TGT 151.13, LH
               321.73, RTX 223.12). Reconstructing it is recovery.

  stop         a DECISION. A candidate that was never opened never had
               one. Inventing 1,013 stops would fabricate decisions nobody
               made - and R3-G exists to ask whether real stop placement
               failed, so a synthetic stop would answer its own question.

So this module reconstructs entry price ONLY, stamps every reconstructed
value with provenance, and leaves `stop_at_pred` exactly as it found it.

PIT SAFETY
----------
`_close_on_or_before(ticker, market, prediction_date)` returns the last
bar dated <= the prediction date. Nothing later can enter. The
reconstruction is therefore replayable and carries no lookahead.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.entry_backfill.v1"
PROVENANCE = "RECONSTRUCTED_FROM_BAR_CLOSE_ON_OR_BEFORE_PREDICTION_DATE"


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def backfill(root: Path, market: str, rows: list) -> dict:
    """Fill missing entry_price_at_pred in place · returns a report."""
    from scripts.build_aegis_3sheet_workbook import _close_on_or_before

    before = sum(1 for r in rows if _num(r.get("entry_price_at_pred")) is not None)
    filled = failed = 0
    cache = {}
    for r in rows:
        if _num(r.get("entry_price_at_pred")) is not None:
            r.setdefault("entry_price_provenance", "SOURCE")
            continue
        t = str(r.get("ticker") or "").upper()
        d = str(r.get("prediction_date") or "")[:10]
        if not t or not d:
            failed += 1
            continue
        key = (t, d)
        if key not in cache:
            try:
                cache[key] = _close_on_or_before(root, t, market, d)
            except Exception:
                cache[key] = None
        px = _num(cache[key])
        if px is None:
            failed += 1
            continue
        r["entry_price_at_pred"] = px
        r["entry_price_provenance"] = PROVENANCE
        filled += 1

    after = sum(1 for r in rows if _num(r.get("entry_price_at_pred")) is not None)
    n = len(rows) or 1
    # The stop is NOT touched · reported so the asymmetry stays visible.
    with_stop = sum(1 for r in rows if _num(r.get("stop_at_pred")) is not None)
    return {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": PROVENANCE,
        "n_rows": len(rows),
        "entry_price_before": before,
        "entry_price_before_pct": round(before / n * 100, 1),
        "entry_price_filled": filled,
        "entry_price_after": after,
        "entry_price_after_pct": round(after / n * 100, 1),
        "unresolvable": failed,
        "stop_at_pred_present": with_stop,
        "stop_at_pred_pct": round(with_stop / n * 100, 1),
        "stop_note": (
            "stop_at_pred is DELIBERATELY NOT backfilled · a stop is a "
            "decision and a never-opened candidate never had one. The "
            "exit cohort is therefore bounded by real stop decisions, not "
            "by entry-price coverage."),
    }


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "cohort"
         / f"entry_backfill_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="PIT-safe entry-price backfill")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rows = load_cohort(root, m)
        rep = backfill(root, m, rows)
        emit(root, rep)
        print(f"entry_backfill:{m} · {rep['entry_price_before_pct']}% -> "
              f"{rep['entry_price_after_pct']}% (+{rep['entry_price_filled']}) "
              f"· unresolvable {rep['unresolvable']} · stop coverage "
              f"{rep['stop_at_pred_pct']}% (untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

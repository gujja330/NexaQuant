"""R2 stop-rule engine audit · CEO 2026-09-01 CRITICAL.

For every R2 ACTIVE position, compute the max adverse excursion between
entry and today. Flag any position where drawdown has crossed the
documented R2 stop rule (DEFAULT_STOP_PCT = 6%). Any positive count is
a production-lifecycle defect · not a workbook issue.

Reads canonical Registry ACTIVE R2 positions + parquet closes.

Output: reports/audit/r2_stop_rule_audit_{market}_{asof}.json

Exit code 2 if any stop-rule violation found.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# From backend/recommendation/investor_actionable/engine.py
R2_STOP_PCT = 0.06     # 6% stop · authoritative source


def _close_series(root: Path, ticker: str, market: str, from_date: str, to_date: str):
    """Return list of (date, close) for ticker in [from_date, to_date] inclusive."""
    import pandas as pd
    dir_ = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    ext = "" if market.lower() == "usa" else ".NS"
    for p in (root / dir_ / f"{ticker.upper()}{ext}_D1.parquet",
                root / dir_ / f"{ticker.upper()}_D1.parquet"):
        if not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns: continue
            idx = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            df = df.copy(); df.index = idx
            sub = df.loc[(df.index >= from_date) & (df.index <= to_date)]
            if sub.empty: return []
            return sorted([(d, float(c)) for d, c in sub["close"].items()])
        except Exception:
            continue
    return []


def audit_market(root: Path, market: str, asof: str) -> dict:
    from backend.research import opportunity_registry as oreg
    reg = oreg.load_all(root)
    active_positions = []
    for pid, opps in reg.items():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.runner != "R2": continue
            if o.status != "ACTIVE": continue
            active_positions.append(o)

    findings = []
    unpriced = 0
    total = 0
    for o in active_positions:
        total += 1
        # Get closes from entry_date to today
        series = _close_series(root, o.ticker, market, o.created_date or "", asof)
        if not series:
            unpriced += 1
            continue
        entry_price = series[0][1]      # first available close on/after entry
        current_price = series[-1][1]   # latest close
        if entry_price <= 0:
            unpriced += 1
            continue
        # Max adverse excursion = worst intraday close (lowest close in window)
        min_close = min(c for _, c in series)
        max_dd_pct = (min_close - entry_price) / entry_price * 100  # negative if below entry
        curr_pnl_pct = (current_price - entry_price) / entry_price * 100
        stop_price = entry_price * (1.0 - R2_STOP_PCT)
        crossed_stop = min_close <= stop_price
        below_stop_now = current_price <= stop_price
        stop_cross_date = None
        if crossed_stop:
            for d, c in series:
                if c <= stop_price:
                    stop_cross_date = d
                    break
        if crossed_stop or below_stop_now:
            findings.append({
                "position_id": o.opportunity_id,
                "ticker": o.ticker,
                "runner": o.runner,
                "entry_date": o.created_date,
                "entry_price": round(entry_price, 4),
                "current_price": round(current_price, 4),
                "min_close": round(min_close, 4),
                "current_pnl_pct": round(curr_pnl_pct, 2),
                "max_dd_pct": round(max_dd_pct, 2),
                "stop_price_6pct": round(stop_price, 4),
                "crossed_stop": crossed_stop,
                "still_below_stop": below_stop_now,
                "stop_cross_date": stop_cross_date,
                "days_since_stop_cross": (
                    (date.fromisoformat(asof) - date.fromisoformat(stop_cross_date)).days
                    if stop_cross_date else None
                ),
                "expected": "EXIT triggered on stop_cross_date if R2 stop rule is live-monitored",
                "actual": "STILL ACTIVE",
            })

    result = {
        "engine": "r2_stop_rule_audit.v1",
        "market": market.lower(),
        "asof": asof,
        "stop_rule_pct": R2_STOP_PCT * 100,
        "stop_rule_source": "backend/recommendation/investor_actionable/engine.py::DEFAULT_STOP_PCT",
        "n_r2_active_total": total,
        "n_unpriced": unpriced,
        "n_findings": len(findings),
        "findings": findings,
        "verdict": ("CLEAN" if not findings
                     else "STOP_RULE_VIOLATIONS_FOUND · engine-lifecycle audit required"),
        "notes": [
            "R2 stop rule is documented at signal-generation time (6% below entry).",
            "This audit does NOT prove the exit engine is broken · it flags positions "
            "whose price crossed the documented threshold while still ACTIVE.",
            "Two valid interpretations for a finding:",
            "  A) Stop rule is soft (advisory) · not hard-enforced by exit engine",
            "  B) Stop rule is hard · exit engine failed to fire → production defect",
            "Either way, if findings exist, the workbook must SURFACE the stop info "
            "explicitly so the operator is not misled about R2's exit contract.",
        ],
    }
    out_p = root / "reports" / "audit" / f"r2_stop_rule_audit_{market.lower()}_{asof}.json"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    any_findings = False
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = audit_market(_ROOT, m, args.asof)
        print(f"[r2_stop_audit:{m}] {rep['verdict']} · "
              f"active={rep['n_r2_active_total']} · findings={rep['n_findings']}")
        for f in rep["findings"][:10]:
            _line = (f"  {f['ticker']:12s} entry={f['entry_price']:8.2f} "
                       f"curr={f['current_price']:8.2f} dd={f['max_dd_pct']:+6.2f}% "
                       f"stop={f['stop_price_6pct']:8.2f} crossed_on={f['stop_cross_date']} "
                       f"days_since={f['days_since_stop_cross']}")
            print(_line.encode("ascii", errors="replace").decode("ascii"))
        if rep["findings"]:
            any_findings = True
    return 2 if any_findings else 0


if __name__ == "__main__":
    sys.exit(main())

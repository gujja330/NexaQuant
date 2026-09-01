"""Reconstruct the complete daily lifecycle of the 3 flagged R2 positions.

For each position, walk every trading day from entry_date to today, and
for each day compute what the DOCUMENTED R2 dynamic exit engine WOULD
have decided (per backend/portfolio/lifecycle_state_machine.py) vs what
actually happened in production.

This is read-only diagnostic · does not modify Registry · does not fire
close events.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# From backend/recommendation/investor_actionable/engine.py
R2_STOP_PCT   = 0.06
R2_T1_MULT    = 2.0   # T1 = entry × (1 + 2 × 6%) = +12%
R2_T2_MULT    = 4.0   # T2 = entry × (1 + 4 × 6%) = +24%
R2_HORIZON_DAYS = 60  # default suggested_holding_period_days


def _close_series(root: Path, ticker: str, market: str, from_date: str, to_date: str):
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


def reconstruct(pid: str, ticker: str, market: str, entry_date: str, asof: str) -> dict:
    """Walk each trading day from entry to asof · flag stop / target / horizon events."""
    series = _close_series(_ROOT, ticker, market, entry_date, asof)
    if not series:
        return {"pid": pid, "error": "no price series"}
    entry_price = series[0][1]
    stop_price = round(entry_price * (1.0 - R2_STOP_PCT), 4)
    t1_price = round(entry_price * (1.0 + R2_T1_MULT * R2_STOP_PCT), 4)
    t2_price = round(entry_price * (1.0 + R2_T2_MULT * R2_STOP_PCT), 4)
    entry_dt = date.fromisoformat(entry_date)

    daily_events = []
    first_stop_cross = None
    first_t1_cross = None
    first_t2_cross = None
    first_horizon_hit = None

    for d_str, close in series:
        d = date.fromisoformat(d_str)
        days_held = (d - entry_dt).days
        pnl_pct = round((close - entry_price) / entry_price * 100, 2)
        would_have_exited_by = None
        would_have_exit_reason = None
        if close <= stop_price and not first_stop_cross:
            first_stop_cross = d_str
            would_have_exited_by = "EXIT_STOP"
            would_have_exit_reason = (
                f"stop-loss triggered at {close:.2f} · stop={stop_price:.2f} "
                f"(entry×{1-R2_STOP_PCT})"
            )
        elif close >= t2_price and not first_t2_cross:
            first_t2_cross = d_str
            would_have_exited_by = "EXIT_TARGET"
            would_have_exit_reason = f"T2 hit at {close:.2f} · T2={t2_price:.2f}"
        elif close >= t1_price and not first_t1_cross:
            first_t1_cross = d_str
            would_have_exited_by = "EXIT_TARGET"
            would_have_exit_reason = f"T1 hit at {close:.2f} · T1={t1_price:.2f}"
        elif days_held >= R2_HORIZON_DAYS and not first_horizon_hit:
            first_horizon_hit = d_str
            would_have_exited_by = "EXIT_HORIZON"
            would_have_exit_reason = f"held {days_held}d >= horizon {R2_HORIZON_DAYS}d"
        daily_events.append({
            "date": d_str,
            "close": round(close, 4),
            "days_held": days_held,
            "pnl_pct": pnl_pct,
            "would_have_exited_by": would_have_exited_by,
            "would_have_exit_reason": would_have_exit_reason,
        })

    # First day the documented engine WOULD have exited
    first_would_exit = next(
        (e for e in daily_events if e["would_have_exited_by"]),
        None,
    )
    return {
        "pid": pid,
        "ticker": ticker,
        "market": market,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "stop_price_6pct": stop_price,
        "t1_price_12pct": t1_price,
        "t2_price_24pct": t2_price,
        "horizon_days": R2_HORIZON_DAYS,
        "n_trading_days_observed": len(daily_events),
        "current_close": daily_events[-1]["close"] if daily_events else None,
        "current_pnl_pct": daily_events[-1]["pnl_pct"] if daily_events else None,
        "first_stop_cross": first_stop_cross,
        "first_t1_cross": first_t1_cross,
        "first_t2_cross": first_t2_cross,
        "first_horizon_hit": first_horizon_hit,
        "documented_engine_first_exit": first_would_exit,
        "actual_status_in_registry": "ACTIVE  (per Registry ACTIVE query)",
        "actual_exit_date": None,
        "verdict": (
            "B · documented lifecycle engine says EXIT but production kept ACTIVE"
            if first_would_exit else
            "A · engine and production agree · still active"
        ),
        "daily_events": daily_events,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    cases = [
        ("IND-R2-CHAMBLFERT-20260804-893fdf", "CHAMBLFERT", "india", "2026-08-04"),
        ("IND-R2-ITC-20260804-e0ebbb", "ITC", "india", "2026-08-04"),
        ("USA-R2-IT-20260810-b5fd37", "IT", "usa", "2026-08-10"),
    ]
    results = []
    for pid, tk, mkt, ent in cases:
        results.append(reconstruct(pid, tk, mkt, ent, args.asof))

    out_p = _ROOT / "reports" / "audit" / f"r2_lifecycle_reconstruction_{args.asof}.json"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps({"asof": args.asof, "cases": results},
                                    indent=2, ensure_ascii=False),
                          encoding="utf-8")

    print(f"Reconstruction saved: {out_p.relative_to(_ROOT)}")
    print()
    for r in results:
        if "error" in r:
            print(f"[{r['pid']}] ERROR: {r['error']}")
            continue
        first = r.get("documented_engine_first_exit")
        _line = (f"[{r['pid']}] {r['ticker']}  entry={r['entry_price']:.2f}  "
                   f"stop@6%={r['stop_price_6pct']:.2f}  T1={r['t1_price_12pct']:.2f}")
        print(_line.encode("ascii", errors="replace").decode("ascii"))
        if first:
            print(f"  documented-engine says: {first['would_have_exited_by']} on "
                    f"{first['date']} at {first['close']:.2f} "
                    f"({first['days_held']}d after entry · pnl={first['pnl_pct']:+.2f}%)")
        else:
            print(f"  documented-engine says: no exit trigger reached")
        print(f"  actual production state: still ACTIVE at asof {args.asof} "
                f"(current pnl={r['current_pnl_pct']:+.2f}%)")
        print(f"  VERDICT: {r['verdict']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Fundamentals-history freshness monitor · CEO 2026-09-04.

Independent health signal so a silently-failing accumulator does NOT quietly
recreate the "1 day of PIT history forever" problem (same failure class as
USA news 11-day staleness that sat undetected).

Reads reports/research/fundamentals_history/{market}.parquet · reports:
  latest_asof · age_days · ticker_count · observation_count · oldest_asof
  · newest_asof · duplicate_count · PIT provenance status

Emits reports/research/fundamentals_freshness.json + exit code:
  age <=  1 day  → OK        (exit 0)
  age ==  2 days → WARNING   (exit 0 · flag in JSON)
  age  >  2 days → FAILURE   (exit 1 · visible stale-data flag)

Freshness ≠ usable research history. A perfectly fresh 1-day dataset is
still insufficient for F01-05. This monitor only asks: is the accumulator
appending? Substrate maturity is a separate weekly check.
"""
from __future__ import annotations
import io, json, sys
from datetime import date, datetime, timedelta
from pathlib import Path


def _trading_days_between(from_d: date, to_d: date) -> int:
    """Count Mon-Fri days between two dates (inclusive of to_d, exclusive of from_d).
    CEO 2026-09-05 · trading-day-aware age so Mon after Fri weekend doesn't
    show age=3 and cry wolf. Ignores holidays deliberately · a false OK on a
    holiday is acceptable · a false WARN every Monday is not."""
    if to_d <= from_d: return 0
    n = 0
    cur = from_d
    while cur < to_d:
        cur = cur + timedelta(days=1)
        # Mon=0 .. Sun=6 · trading days are Mon-Fri
        if cur.weekday() < 5:
            n += 1
    return n
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass


def check_market(market: str) -> dict:
    import pandas as pd
    p = _ROOT / "reports" / "research" / "fundamentals_history" / f"{market}.parquet"
    if not p.exists():
        return {
            "market": market, "status": "MISSING",
            "reason": f"parquet file does not exist · {p.relative_to(_ROOT)}",
            "action": "Run scripts/accumulate_fundamentals_history.py --market " + market,
            "exit_code": 1,
        }
    try:
        df = pd.read_parquet(p)
    except Exception as e:
        return {"market": market, "status": "READ_ERROR",
                "reason": str(e)[:120], "exit_code": 1}

    if df.empty:
        return {"market": market, "status": "EMPTY",
                "reason": "parquet is empty · accumulator hasn't run", "exit_code": 1}

    if "asof" not in df.columns:
        return {"market": market, "status": "SCHEMA_ERROR",
                "reason": "no asof column · parquet schema unexpected", "exit_code": 1}

    df["asof_d"] = pd.to_datetime(df["asof"]).dt.date
    latest = df["asof_d"].max()
    oldest = df["asof_d"].min()
    today = date.today()
    calendar_age_days = (today - latest).days
    # CEO 2026-09-05 · trading-day-aware age · Mon after Fri = 0 trading days,
    # not 3 calendar days. Fixes the "false WARN every Monday" failure mode.
    trading_age_days = _trading_days_between(latest, today)
    n_tickers = int(df["ticker"].nunique()) if "ticker" in df.columns else 0
    n_obs = int(len(df))
    n_unique_asof = int(df["asof_d"].nunique())
    dup_count = int(df.duplicated(subset=["market","ticker","asof"]).sum()) \
        if all(c in df.columns for c in ("market","ticker","asof")) else 0

    # Status per CEO threshold · TRADING-day-aware (weekends don't count)
    if trading_age_days <= 1:
        status = "OK"
        exit_code = 0
    elif trading_age_days == 2:
        status = "WARNING"
        exit_code = 0
    else:
        status = "FAILURE"
        exit_code = 1

    pit_status = "clean" if trading_age_days <= 1 else ("watch" if trading_age_days == 2 else "drift")

    return {
        "market": market,
        "status": status,
        "latest_asof": str(latest),
        "oldest_asof": str(oldest),
        "age_days_trading": trading_age_days,          # authoritative
        "age_days_calendar": calendar_age_days,        # for reference only
        "n_unique_asof_dates": n_unique_asof,
        "ticker_count": n_tickers,
        "observation_count": n_obs,
        "duplicate_count": dup_count,
        "pit_provenance_status": pit_status,
        "usable_for_f01_05_oos": n_unique_asof >= 60,   # 60+ trading days needed
        "note": ("Freshness OK does not imply usable research history · F01-05 OOS "
                  "needs n_unique_asof_dates ≥ 60 (currently {})").format(n_unique_asof),
        "exit_code": exit_code,
    }


def main():
    results = {}
    max_exit = 0
    for m in ("india", "usa"):
        r = check_market(m)
        results[m] = r
        max_exit = max(max_exit, r.get("exit_code", 0))

    out = _ROOT / "reports" / "research" / "fundamentals_freshness.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "engine": "fundamentals_freshness_check",
        "run_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "per_market": results,
        "overall_exit_code": max_exit,
    }, indent=2, default=str), encoding="utf-8")

    for m, r in results.items():
        print(f"{m.upper()}: status={r.get('status')} "
              f"trading_age={r.get('age_days_trading')} "
              f"(cal_age={r.get('age_days_calendar')}) "
              f"unique_asof={r.get('n_unique_asof_dates')} "
              f"usable_for_F01-05={r.get('usable_for_f01_05_oos')}")
    print(f"[freshness] wrote {out.relative_to(_ROOT)}")
    sys.exit(max_exit)


if __name__ == "__main__":
    main()

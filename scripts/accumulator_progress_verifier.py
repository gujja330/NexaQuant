"""Accumulator progress verifier · CEO 2026-09-05.

Operational check that the fundamentals accumulator is GENUINELY advancing
PIT history · not just wired into CI. If tomorrow's run still shows
unique_asof_dates=1, the accumulator is broken · this script surfaces that
with an exit-1 flag visible in 00_Health.

Tracks a rolling history file · reports/research/accumulator_progress.jsonl ·
one line per verifier run · so we can watch the day-by-day trajectory:

    Day 1: 1 asof date
    Day 2: 2
    Day 3: 3
    ...
    Day 30: >=30
    Day 50+: validation candidate

Fails-closed if:
  - accumulator ran but did not add a new asof today
  - asof count moved BACKWARDS (would indicate corruption)
  - India or USA parquet missing when the other exists
"""
from __future__ import annotations
import io, json, sys
from datetime import date, datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass


PROGRESS_LOG = _ROOT / "reports" / "research" / "accumulator_progress.jsonl"


def _current_state(market: str) -> dict:
    import pandas as pd
    p = _ROOT / "reports" / "research" / "fundamentals_history" / f"{market}.parquet"
    if not p.exists():
        return {"market": market, "exists": False}
    df = pd.read_parquet(p)
    if df.empty:
        return {"market": market, "exists": True, "empty": True}
    return {
        "market": market,
        "exists": True,
        "empty": False,
        "n_rows": int(len(df)),
        "n_unique_asof": int(df["asof"].nunique()),
        "latest_asof": str(pd.to_datetime(df["asof"]).max().date()),
        "oldest_asof": str(pd.to_datetime(df["asof"]).min().date()),
        "n_unique_tickers": int(df["ticker"].nunique()),
    }


def _previous_state(market: str) -> dict | None:
    """Return the most recent verifier record for this market · None if first run."""
    if not PROGRESS_LOG.exists(): return None
    for line in reversed(PROGRESS_LOG.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line: continue
        try:
            r = json.loads(line)
            if r.get("market") == market: return r
        except Exception: pass
    return None


def _verify(current: dict, previous: dict | None) -> dict:
    """Compare current vs previous · emit status + reason."""
    m = current["market"]
    if not current.get("exists"):
        return {"status": "FAIL", "reason": f"{m} parquet does not exist"}
    if current.get("empty"):
        return {"status": "FAIL", "reason": f"{m} parquet is empty"}

    n_now = current["n_unique_asof"]
    if previous is None:
        # First-ever run · anything ≥1 is OK, we're establishing baseline
        return {"status": "BASELINE", "reason": f"first verifier run · baseline={n_now} asof"}

    n_prev = previous.get("n_unique_asof", 0)
    if n_now < n_prev:
        return {"status": "FAIL",
                 "reason": f"{m} asof count went BACKWARDS · was {n_prev} now {n_now} · data corruption"}
    if n_now == n_prev:
        # Only OK if today is Sat/Sun (no cron on weekends)
        today_wd = date.today().weekday()
        if today_wd >= 5:
            return {"status": "WEEKEND_OK",
                     "reason": f"{m} unchanged at {n_now} · weekend day {today_wd} · no cron expected"}
        return {"status": "STALLED",
                 "reason": f"{m} asof count did not advance · was {n_prev} still {n_prev} · accumulator may be broken"}
    return {"status": "PROGRESSING",
             "reason": f"{m} advanced from {n_prev} to {n_now} unique asof dates"}


def main():
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    records = []
    overall_exit = 0
    for market in ("india", "usa"):
        current = _current_state(market)
        previous = _previous_state(market)
        verdict = _verify(current, previous)
        record = {
            "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_date": date.today().isoformat(),
            "market": market,
            **current,
            **verdict,
        }
        records.append(record)
        # Append immutably to log
        with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        print(f"{market.upper()}: n_asof={current.get('n_unique_asof','?')} "
              f"latest={current.get('latest_asof','?')} · status={verdict['status']} · "
              f"{verdict['reason']}")
        # Fail conditions
        if verdict["status"] in ("FAIL", "STALLED"):
            overall_exit = 1

    # Also emit summary JSON for 00_Health cockpit consumption
    summary_p = _ROOT / "reports" / "research" / "accumulator_progress_summary.json"
    summary_p.write_text(json.dumps({
        "engine": "accumulator_progress_verifier",
        "run_utc": records[0]["run_utc"] if records else datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "per_market": {r["market"]: r for r in records},
        "overall_exit": overall_exit,
    }, indent=2, default=str), encoding="utf-8")
    print(f"[verifier] wrote {summary_p.relative_to(_ROOT)}")
    sys.exit(overall_exit)


if __name__ == "__main__":
    main()

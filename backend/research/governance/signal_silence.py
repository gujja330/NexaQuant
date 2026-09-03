"""Signal Silence trigger (8th Research Trigger) + Minimum Viable Signal floor.

Sprint A · CEO 2026-09-03 · pasted-plan §9.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

SILENCE_MIN_DAYS = 10
MVS_MIN_SIGNALS = 3
RELAXATION_CAP_PER_90D = 15


def evaluate_signal_silence(runner: str,
                            zero_days_streak: int,
                            trailing_avg_daily_signals: float,
                            all_runners_silent: bool) -> dict:
    """Returns { fired, reason }.

    Rule:
      fires iff zero_days_streak >= 10
              AND trailing_avg_daily_signals > 0.5 (runner normally produces)
              AND not all_runners_silent (all-market silence isn't runner-specific).
    """
    if all_runners_silent:
        return {"fired": False, "reason": "ALL_RUNNERS_SILENT · likely genuine market absence"}
    if zero_days_streak < SILENCE_MIN_DAYS:
        return {"fired": False, "reason": f"streak={zero_days_streak} < {SILENCE_MIN_DAYS}"}
    if trailing_avg_daily_signals <= 0.5:
        return {"fired": False, "reason": f"trailing_avg={trailing_avg_daily_signals} · runner dormant by baseline"}
    return {"fired": True, "reason": (
        f"Runner {runner} silent {zero_days_streak}d while trailing_avg="
        f"{trailing_avg_daily_signals:.2f} · investigate")}


def evaluate_mvs_floor(n_qualifying_today: int,
                       min_signals: int = MVS_MIN_SIGNALS) -> dict:
    """Returns { below_floor, n, floor, action }."""
    if n_qualifying_today >= min_signals:
        return {"below_floor": False, "n": n_qualifying_today,
                "floor": min_signals, "action": "NORMAL"}
    return {"below_floor": True, "n": n_qualifying_today,
            "floor": min_signals,
            "action": "GATE_RELAXED_RERUN_OPERATOR_FLAG"}


class RelaxationTracker:
    """Rolling 90-day counter · caps gate-relaxation to 15 events per window.

    Persists to reports/research/governance/relaxation_log.jsonl · append-only.
    """

    def __init__(self, root: Path):
        self.log_path = root / "reports" / "research" / "governance" / "relaxation_log.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.log_path.exists(): return []
        out = []
        with self.log_path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln: continue
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
        return out

    def count_last_90d(self, asof: str) -> int:
        events = self._load()
        try:
            asof_d = datetime.fromisoformat(asof).date()
        except ValueError:
            return 0
        cutoff = asof_d - timedelta(days=90)
        return sum(1 for e in events
                   if e.get("date") and
                   datetime.fromisoformat(e["date"]).date() >= cutoff)

    def can_relax(self, asof: str) -> dict:
        used = self.count_last_90d(asof)
        remaining = RELAXATION_CAP_PER_90D - used
        return {
            "allowed": remaining > 0,
            "used_last_90d": used,
            "cap": RELAXATION_CAP_PER_90D,
            "remaining": remaining,
        }

    def record_relaxation(self, asof: str, market: str, reason: str) -> dict:
        entry = {
            "date": asof, "market": market, "reason": reason,
            "ts_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return entry

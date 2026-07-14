"""
MON001 alert pipeline.

Severity levels (in ascending order of urgency):
- INFO                    : informational; no operator action required
- WARN                    : degraded state; operator should review at convenience
- HALT_REVIEW_REQUIRED    : blocking condition; operator action REQUIRED before continuing

Every alert emitted here appends to `reports/mon001_alerts.jsonl` (append-only) with:
- timestamp (UTC)
- dimension (which drift dimension or subsystem)
- severity
- reason
- first_occurrence timestamp (for the same dimension+severity across recent runs)
- consecutive_occurrences count (weekly-window based)
- recommended_action human string

Alert history is used by run_mon001.py to escalate DIVERGED → HALT_REVIEW_REQUIRED after
4 consecutive weekly reports of persistence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from pathlib import Path


SEVERITY_ORDER = {"INFO": 0, "WARN": 1, "HALT_REVIEW_REQUIRED": 2}


RECOMMENDED_ACTION = {
    "D1_CONFIG_DRIFT":
        "Production baseline changed. Do NOT proceed without operator authorization. "
        "Compare the current fingerprint against the sealed hash; if the change is "
        "authorized (a promotion via a separate change management process), re-seal "
        "MON001 by removing reports/sealed_fingerprint.json and rerunning with "
        "--seal-init. If unauthorized, revert the production change.",
    "D2_PERFORMANCE_DRIFT":
        "Forward Sharpe deviated from LAB009 envelope. Review the last N weekly "
        "reports; if divergence persists 4 consecutive weeks, MON001 will escalate "
        "to HALT_REVIEW_REQUIRED automatically. Do NOT tune the strategy in "
        "response — that would be post-hoc search on live evidence.",
    "D3_RISK_DRIFT":
        "Forward MaxDD deeper than backtested envelope × buffer. Confirm no data "
        "quality issue; check for a regime shift. Persistent 4-week divergence "
        "escalates to HALT.",
    "D4_TURNOVER_DRIFT":
        "Realized turnover exceeds backtest mean × threshold. Confirm rebalance "
        "cadence hasn't been altered by an out-of-schedule generator run.",
    "D5_COST_DRIFT":
        "Realized cost exceeds envelope. If broker fills are available, review "
        "individual trade slippage. Otherwise, verify turnover measurement is on "
        "a paper-cost basis and consistent with the envelope.",
    "D6_REGIME_BEHAVIOUR_DRIFT":
        "Forward exposure per regime bucket diverges from backtest exposure. "
        "Verify `current_regime()` computes identically (fingerprint should catch this "
        "unless the change was silent).",
    "D7_CONCENTRATION_DRIFT":
        "name_cap or sector_cap breached in a forward observation. This is a portfolio "
        "construction violation — investigate the generator run that produced the offending "
        "batch. Do NOT ignore — this is a hard constraint, not a soft envelope.",
    "D8_DATA_DRIFT":
        "Forward ledger has too many missing prices or stale recommendations. "
        "Check the data-refresh pipeline (yfinance / Angel pull) and the scoring "
        "cadence (recommendations mature but don't get their exit_price populated).",
    "D9_EXECUTION_DRIFT":
        "Realized slippage exceeds threshold (only meaningful when broker fills are "
        "ingested; currently PAPER_ONLY).",
    "D10_DATA_INTEGRITY_FAILURE":
        "Ledger tampered with or corrupted. Do NOT proceed. Preserve the current "
        "ledger file for forensics; restore from the last known-good backup; "
        "investigate root cause before resuming MON001.",
    "OPS_RUN_FAILED":
        "MON001 daily runner encountered an unexpected exception. Investigate the "
        "stack trace in the ops log. Recommendation generation is NOT affected — "
        "MON001 failure is isolated from the production pipeline.",
    "OPS_MARKET_CLOSED":
        "Ran on a non-trading day (weekend or NSE holiday). No action required; "
        "MON001 emits a 'market closed' status report and moves on.",
    "OPS_DATA_STALE":
        "Freshness check found market data older than the previous trading session. "
        "MON001 still runs (fingerprint + ledger integrity checks are useful) but "
        "metric evaluation is deferred until data refreshes.",
}


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Alert:
    timestamp_utc: str
    dimension: str
    severity: str
    reason: str
    first_occurrence: str | None = None
    consecutive_occurrences: int = 1
    recommended_action: str = ""
    context: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class AlertBus:
    """Append-only alert log with occurrence tracking."""

    def __init__(self, alerts_path: str | Path):
        self.path = Path(alerts_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def _consecutive_and_first(self, dimension: str, severity: str,
                                 today: date | None = None) -> tuple[int, str | None]:
        """Count consecutive weekly windows where (dimension, severity) has been active,
        walking back from today. Returns (count, first_occurrence_iso)."""
        rows = self.read_all()
        if not rows:
            return 1, None
        today = today or date.today()
        weeks: dict[str, str] = {}
        for r in rows:
            if r.get("dimension") != dimension or r.get("severity") != severity:
                continue
            ts = r.get("timestamp_utc", "")[:10]
            if not ts:
                continue
            try:
                d = date.fromisoformat(ts)
                iy, iw, _ = d.isocalendar()
                key = f"{iy}-W{iw:02d}"
                if key not in weeks or ts < weeks[key]:
                    weeks[key] = ts
            except ValueError:
                continue
        if not weeks:
            return 1, None
        iy_today, iw_today, _ = today.isocalendar()
        cur_key = f"{iy_today}-W{iw_today:02d}"
        count = 0
        first_seen: str | None = None
        y, w = iy_today, iw_today
        for _ in range(53):
            key = f"{y}-W{w:02d}"
            if key in weeks:
                count += 1
                first_seen = weeks[key]
                w -= 1
                if w <= 0:
                    y -= 1
                    w = 52
            else:
                break
        return max(1, count + 1), first_seen

    def emit(self, dimension: str, severity: str, reason: str,
             context: dict | None = None) -> Alert:
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"unknown severity {severity!r}")
        consecutive, first = self._consecutive_and_first(dimension, severity)
        alert = Alert(
            timestamp_utc=_iso_utc(),
            dimension=dimension,
            severity=severity,
            reason=reason,
            first_occurrence=first,
            consecutive_occurrences=consecutive,
            recommended_action=RECOMMENDED_ACTION.get(dimension,
                "No specific playbook — treat according to severity."),
            context=(context or {}),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(alert.as_dict(), ensure_ascii=False, default=str) + "\n")
        return alert

    def recent(self, n: int = 20) -> list[dict]:
        rows = self.read_all()
        return rows[-n:]

    def active(self, min_severity: str = "WARN") -> list[dict]:
        """Return alerts from the last 7 days at or above the given severity."""
        rows = self.read_all()
        cutoff = _cutoff_iso(7)
        threshold = SEVERITY_ORDER[min_severity]
        return [r for r in rows
                if r.get("timestamp_utc", "") >= cutoff
                and SEVERITY_ORDER.get(r.get("severity", "INFO"), 0) >= threshold]


def _cutoff_iso(days_back: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat(timespec="seconds")

"""Freshness validator.

Reads file mtime + optionally the file's own `run_utc` / `latest_date`
field, compares against expected refresh cadence from dataset spec.

Verdicts:
  PASS     — refreshed within SLA
  WARNING  — 1 trading day overdue
  FAIL     — 2+ trading days overdue OR file missing entirely
  NOT_APPLICABLE — dataset marked optional and absent
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .base import Validator, ValidationResult, Verdict, Issue, Severity


class FreshnessValidator(Validator):
    name = "freshness"

    def __init__(self, weekend_aware: bool = True, *, market: str = ""):
        self.weekend_aware = weekend_aware
        self.market = market

    def _trading_days_between(self, a: datetime, b: datetime) -> int:
        """Business days between two dates (exclusive-exclusive)."""
        if a > b: a, b = b, a
        if self.market == "india":
            from scripts.check_data_freshness import NSE_HOLIDAYS_2026, NSE_IST

            start = a.astimezone(NSE_IST).date()
            end = b.astimezone(NSE_IST).date()
            return sum(day.date() > start and day.date() not in NSE_HOLIDAYS_2026
                       for day in pd.bdate_range(start, end))
        return len(pd.bdate_range(a.date(), b.date())) - 1

    def validate(self, spec: dict, root: Path) -> ValidationResult:
        t0 = time.time()
        path = root / spec["path"]
        dataset = spec["name"]
        optional = spec.get("optional", False)
        sla_days = spec.get("freshness_sla_trading_days", 1)

        issues = []; evidence = {}; suggested = []

        if not path.exists():
            if optional:
                return ValidationResult(
                    validator=self.name, dataset=dataset, verdict=Verdict.NOT_APPLICABLE,
                    confidence=1.0, evidence={"path": str(path), "reason": "optional_missing"},
                    elapsed_ms=(time.time() - t0) * 1000)
            issues.append(Issue(Severity.CRITICAL, f"{path} does not exist",
                                 {"path": str(path)}))
            suggested.append(f"Run the producer script for {dataset}")
            return ValidationResult(
                validator=self.name, dataset=dataset, verdict=Verdict.FAIL,
                confidence=1.0, issues=issues, evidence={"path": str(path)},
                suggested_fixes=suggested, elapsed_ms=(time.time() - t0) * 1000)

        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        wall_hours_old = (now - mtime).total_seconds() / 3600
        trading_days_old = self._trading_days_between(mtime, now) if self.weekend_aware else int(wall_hours_old / 24)

        evidence.update({
            "path":              str(path),
            "mtime_utc":         mtime.isoformat(timespec="seconds"),
            "wall_hours_old":    round(wall_hours_old, 2),
            "trading_days_old":  trading_days_old,
            "sla_trading_days":  sla_days,
        })

        if self.market == "india" and spec.get("kind") == "price" and path.suffix == ".parquet":
            from scripts.check_data_freshness import completed_nse_session, NSE_IST

            sessions = pd.read_parquet(path, columns=[]).index
            actual = pd.to_datetime(sessions).max()
            expected = completed_nse_session(now)
            evidence["expected_completed_session"] = expected.isoformat()
            if pd.isna(actual) or actual.date() > expected:
                issues.append(Issue(Severity.CRITICAL, "Missing completed bars or unfinalized bar present"))
                return ValidationResult(
                    validator=self.name, dataset=dataset, verdict=Verdict.FAIL, confidence=1.0,
                    issues=issues, evidence=evidence, elapsed_ms=(time.time() - t0) * 1000,
                )
            actual_date = actual.date()
            trading_days_old = self._trading_days_between(
                datetime.combine(actual_date, datetime.min.time(), tzinfo=NSE_IST),
                datetime.combine(expected, datetime.min.time(), tzinfo=NSE_IST),
            )
            evidence["price_session"] = actual_date.isoformat()
            evidence["trading_days_old"] = trading_days_old

        # Try to read run_utc from JSON payload for a more authoritative timestamp
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                run_utc = data.get("run_utc")
                if run_utc:
                    evidence["run_utc_declared"] = run_utc
            except Exception:
                pass

        if trading_days_old <= sla_days:
            verdict = Verdict.PASS
            conf = 1.0
        elif trading_days_old <= sla_days + 1:
            verdict = Verdict.WARNING
            conf = 0.7
            issues.append(Issue(Severity.WARNING,
                                 f"1 trading day overdue (SLA {sla_days} · currently {trading_days_old})",
                                 {"trading_days_old": trading_days_old}))
            suggested.append(f"Investigate why the producer of {dataset} hasn't refreshed")
        else:
            verdict = Verdict.FAIL
            conf = 0.3
            issues.append(Issue(Severity.CRITICAL,
                                 f"{trading_days_old} trading days overdue (SLA {sla_days})",
                                 {"trading_days_old": trading_days_old}))
            suggested.append(f"Producer of {dataset} needs immediate investigation — possibly a broken pipeline step")

        return ValidationResult(
            validator=self.name, dataset=dataset, verdict=verdict, confidence=conf,
            issues=issues, evidence=evidence, suggested_fixes=suggested,
            elapsed_ms=(time.time() - t0) * 1000)

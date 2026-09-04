"""AEGIS Standard Testing Pattern (STP) · CEO 2026-09-04.

Default 5-test pattern applied to EVERY research module + upgrade.
No need to request the pattern for each candidate · this IS the pattern.

  T1 · BACKEND UNIT · math + edge cases + insufficient-data handling
  T2 · BACKEND INTEGRATION · runs on real repo data · both markets
  T3 · BACKWARD WALK-FORWARD · 70/30 temporal split (or ticker-split if temporal blocked)
  T4 · FORWARD LAST-60-DAYS · train on data BEFORE last 60 days · evaluate on last 60d
  T5 · FRONTEND · if research affects delivery, verify workbook still renders + values sane

Each test emits {status: PASS | FAIL | BLOCKED | N/A, note: str, metric: dict}.

WORTH VERDICT combines the results:
  - WORTH        · at least T3+T4 both PASS · and if T5 required, T5 PASS
  - CONDITIONAL  · T3 PASS but T4 fail-or-marginal · needs monitoring cycle
  - NOT_WORTH    · T3 FAIL · or T4 shows negative lift · reject
  - BLOCKED      · T3 or T4 BLOCKED by data availability · re-run when unblocked

Dynamic · both markets · no hardcoded thresholds.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Callable, Optional


LAST_60D_WINDOW = 60          # CEO's canonical forward-test horizon
DSR_P_ACCEPTANCE = 0.10       # multiple-testing gate
MIN_SAMPLE = 30               # V2 stronger-evidence tier (validation candidate = 50)


@dataclass
class TestResult:
    status: str                    # PASS | FAIL | BLOCKED | N/A
    note: str = ""
    metric: dict = field(default_factory=dict)


@dataclass
class STPReport:
    research_id: str
    market: str
    T1_backend_unit: TestResult
    T2_backend_integration: TestResult
    T3_backward_walkforward: TestResult
    T4_forward_last60d: TestResult
    T5_frontend: TestResult
    worth_verdict: str = ""        # WORTH | CONDITIONAL | NOT_WORTH | BLOCKED
    worth_reason: str = ""
    generated_utc: str = ""


def synthesize_worth(t1: TestResult, t2: TestResult, t3: TestResult,
                      t4: TestResult, t5: TestResult) -> tuple[str, str]:
    """Standard worth-synthesis rule · applied uniformly."""
    # Data availability
    if t3.status == "BLOCKED" and t4.status == "BLOCKED":
        return "BLOCKED", f"Both T3 and T4 blocked · {t3.note or t4.note}"
    if t1.status == "FAIL":
        return "NOT_WORTH", f"Backend unit tests fail · math or edge case broken · {t1.note}"
    if t2.status == "FAIL":
        return "NOT_WORTH", f"Integration test fail · module does not run on real data · {t2.note}"

    # Core research verdict from T3 + T4
    t3_ok = t3.status == "PASS"
    t4_ok = t4.status == "PASS"
    t3_bl = t3.status == "BLOCKED"
    t4_bl = t4.status == "BLOCKED"

    if t3_ok and t4_ok:
        if t5.status in ("FAIL",):
            return "NOT_WORTH", f"Backward + forward pass but frontend renders wrong · {t5.note}"
        return "WORTH", f"T3 backward + T4 forward-60d both PASS · lift confirmed OOS"
    if t3_ok and t4_bl:
        return "CONDITIONAL", f"T3 backward PASS · T4 forward blocked ({t4.note}) · monitor + re-run"
    if t3_ok and not t4_ok:
        return "CONDITIONAL", (f"T3 backward PASS but T4 forward-60d shows lift="
                                f"{t4.metric.get('lift_pct','?')}% (below gate) · monitor + re-run in 4 weeks")
    if t3_bl and t4_ok:
        return "CONDITIONAL", "T3 backward blocked but T4 forward-60d PASS · thin evidence · monitor"
    return "NOT_WORTH", (f"T3={t3.status} T4={t4.status} · does not clear worth gate · "
                          f"preserve REJECT verdict · do not promote")


def run_stp(research_id: str, market: str,
            t1_fn: Callable[[], TestResult],
            t2_fn: Callable[[], TestResult],
            t3_fn: Callable[[], TestResult],
            t4_fn: Callable[[], TestResult],
            t5_fn: Optional[Callable[[], TestResult]] = None) -> STPReport:
    """Run the standard 5-test pattern · return report + auto-derived worth verdict."""
    t1 = t1_fn() if t1_fn else TestResult("N/A", "no unit test defined")
    t2 = t2_fn() if t2_fn else TestResult("N/A", "no integration test defined")
    t3 = t3_fn() if t3_fn else TestResult("N/A", "no backward walk-forward defined")
    t4 = t4_fn() if t4_fn else TestResult("N/A", "no forward last-60d test defined")
    t5 = t5_fn() if t5_fn else TestResult("N/A", "research does not affect delivery")
    verdict, reason = synthesize_worth(t1, t2, t3, t4, t5)
    return STPReport(
        research_id=research_id,
        market=market,
        T1_backend_unit=t1, T2_backend_integration=t2,
        T3_backward_walkforward=t3, T4_forward_last60d=t4, T5_frontend=t5,
        worth_verdict=verdict, worth_reason=reason,
        generated_utc=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def emit_stp_report(root: Path, report: STPReport) -> Path:
    out_dir = root / "reports" / "research" / "stp"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{report.research_id.lower().replace('_','-')}_{report.market}.json"
    p.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    return p


def format_worth_table(reports: list[STPReport]) -> str:
    """Return a markdown table summarising WORTH verdicts across items."""
    out = ["| Research ID | Market | T1 unit | T2 integ | T3 backward | T4 forward-60d | T5 frontend | **WORTH** |",
             "|---|---|---|---|---|---|---|---|"]
    for r in reports:
        out.append(
            f"| {r.research_id} | {r.market} | {r.T1_backend_unit.status} "
            f"| {r.T2_backend_integration.status} | {r.T3_backward_walkforward.status} "
            f"| {r.T4_forward_last60d.status} | {r.T5_frontend.status} "
            f"| **{r.worth_verdict}** |"
        )
    return "\n".join(out)

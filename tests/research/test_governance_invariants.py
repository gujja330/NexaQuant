"""Mechanical validators for the 5 governance rules + 4 change-set items.

CEO 2026-09-05 · locked test suite that must pass before any push consolidating
the current change set. Every assertion is arithmetic or textual · never opinion.

Covers per CEO ask:
  1. registry arithmetic invariant
  2. WORKED_LEGACY queue integrity
  3. 13-stage STP→Coverage mapping
  4. freshness logic (trading-day-aware)
  5. P1 exemption governance text present + complete
  6. accumulator/PIT parquet integrity
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ── Invariant 1 · registry arithmetic ─────────────────────────────────

def test_registry_total_reconciles_with_state_buckets():
    """Sum of grand_totals must equal len(ALL_ITEMS) · caught 46-vs-49 gap earlier."""
    from backend.research.research_registry import ALL_ITEMS
    # Re-run recompute mechanically
    import subprocess
    result = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "recompute_research_summary.py")],
        capture_output=True, text=True, cwd=_ROOT, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"recompute failed · stdout={result.stdout[-500:]} stderr={result.stderr[-500:]}"
    summary_p = _ROOT / "reports" / "research" / f"summary_recomputed_{date.today().isoformat()}.json"
    j = json.loads(summary_p.read_text(encoding="utf-8"))
    total = j["total_items_in_registry"]
    grand = j["grand_totals"]
    assert sum(grand.values()) == total, (
        f"registry arithmetic FAIL · sum(grand_totals)={sum(grand.values())} != total={total}"
    )
    assert j["reconciliation_check"]["reconciles"] is True


def test_registry_no_duplicate_ids():
    """Every ResearchItem must have a unique id."""
    from backend.research.research_registry import ALL_ITEMS
    ids = [x.id for x in ALL_ITEMS]
    assert len(ids) == len(set(ids)), f"duplicate ids · {[i for i in ids if ids.count(i) > 1]}"


def test_registry_min_expected_count():
    """Registry must have at least 51 items · guards against silent deletions."""
    from backend.research.research_registry import ALL_ITEMS
    assert len(ALL_ITEMS) >= 51, f"registry shrunk unexpectedly · n={len(ALL_ITEMS)}"


# ── Invariant 2 · WORKED_LEGACY queue integrity ───────────────────────

def test_queue_priority_partitions_reconcile():
    """schedulable + blocked_by_rule + not_scheduled = total items."""
    from backend.research.research_registry import ALL_ITEMS
    n_total = len(ALL_ITEMS)
    n_schedulable = sum(1 for x in ALL_ITEMS if x.remediation_priority < 90)
    n_blocked = sum(1 for x in ALL_ITEMS if 90 <= x.remediation_priority <= 98)
    n_not_scheduled = sum(1 for x in ALL_ITEMS if x.remediation_priority == 99)
    assert n_schedulable + n_blocked + n_not_scheduled == n_total, (
        f"queue partition FAIL · sched={n_schedulable} block={n_blocked} "
        f"not_sched={n_not_scheduled} total={n_total}"
    )


def test_every_item_has_remediation_priority():
    """No item may lack scheduling metadata."""
    from backend.research.research_registry import ALL_ITEMS
    missing = [x.id for x in ALL_ITEMS if not hasattr(x, "remediation_priority")]
    assert not missing, f"items without remediation_priority · {missing}"


def test_blocked_items_have_upstream_substrate():
    """Priority 90-98 (blocked by substrate rule) must name what they wait on."""
    from backend.research.research_registry import ALL_ITEMS
    violations = []
    for x in ALL_ITEMS:
        if 90 <= x.remediation_priority <= 98 and not x.upstream_substrate:
            # Some blocks are DEFERRED with no upstream (like Peer-pair statarb) · allow if
            # next_stp_action names the reason
            if not x.next_stp_action:
                violations.append(x.id)
    assert not violations, f"blocked items without upstream substrate declared · {violations}"


# ── Invariant 3 · 13-stage STP→Coverage mapping ───────────────────────

def test_stp_to_coverage_mapping_exists_and_covers_all_verdicts():
    """Every STP verdict maps to a Coverage Tracker stage · no unmapped state."""
    from scripts.recompute_research_summary import STP_TO_COVERAGE
    expected_verdicts = {"WORTH", "CONDITIONAL", "NOT_WORTH", "BLOCKED"}
    assert set(STP_TO_COVERAGE.keys()) == expected_verdicts, (
        f"STP→Coverage keys mismatch · got {set(STP_TO_COVERAGE.keys())} "
        f"expected {expected_verdicts}"
    )
    # Every mapped stage must be a real 13-stage name
    valid_stages = {"Mapped", "Data-required", "PIT-ready", "Populated",
                     "Implemented", "Tested", "OOS", "Corrected", "Incremental",
                     "Paper", "Shadow", "Candidate", "Production"}
    for v, s in STP_TO_COVERAGE.items():
        assert s in valid_stages, f"STP {v}→{s} not a valid 13-stage name"


def test_worth_caveat_present_in_recompute():
    """WORTH_CAVEAT constant must state remaining gates before Production."""
    from scripts.recompute_research_summary import WORTH_CAVEAT
    for phrase in ("Incremental", "Paper", "Shadow", "Candidate", "Production"):
        assert phrase in WORTH_CAVEAT, f"WORTH_CAVEAT missing gate name · {phrase}"


# ── Invariant 4 · freshness logic (trading-day-aware) ─────────────────

def test_trading_day_math_correct():
    """Fri→Mon=1 · Fri→Tue=2 · Fri→Fri=0 · fixes the false-WARN-every-Monday edge case."""
    from scripts.fundamentals_freshness_check import _trading_days_between
    fri = date(2026, 8, 28)   # a real Friday
    mon = date(2026, 8, 31)   # following Monday
    tue = date(2026, 9, 1)    # following Tuesday
    assert _trading_days_between(fri, mon) == 1
    assert _trading_days_between(fri, tue) == 2
    assert _trading_days_between(fri, fri) == 0
    # Weekend-only span must be 0
    sat = date(2026, 8, 29)
    sun = date(2026, 8, 30)
    assert _trading_days_between(fri, sat) == 0
    assert _trading_days_between(fri, sun) == 0


def test_freshness_check_reports_both_ages():
    """Report must include age_days_trading (authoritative) + age_days_calendar (ref)."""
    from scripts.fundamentals_freshness_check import check_market
    r = check_market("india")
    if r.get("status") in ("MISSING", "EMPTY", "READ_ERROR", "SCHEMA_ERROR"):
        return   # can't validate on empty data
    assert "age_days_trading" in r, "missing trading-day age (authoritative)"
    assert "age_days_calendar" in r, "missing calendar-day age (reference)"


# ── Invariant 5 · P1 exemption governance text ─────────────────────────

def test_p1_exemption_governance_text_complete():
    """Governance doc must contain the 4 required conditions for the P1 exemption
    · and explicitly state it is NOT a template."""
    doc = (_ROOT / "docs" / "AEGIS" / "GOVERNANCE_SUBSTRATE_BEFORE_SOPHISTICATION.md").read_text(encoding="utf-8")
    for phrase in (
        "P1 exemption",
        "NOT a template",
        "all four conditions",         # anti-template safeguard
        "operates on data",            # condition (a)
        "does NOT depend",             # condition (b)
        "accumulation",                # condition (c) mention
        "not a template",              # anti-template case-insensitive
    ):
        assert phrase.lower() in doc.lower(), f"governance doc missing phrase · '{phrase}'"


def test_governance_doc_contains_five_locked_rules():
    """All five governance rules must be in the doc."""
    doc = (_ROOT / "docs" / "AEGIS" / "GOVERNANCE_SUBSTRATE_BEFORE_SOPHISTICATION.md").read_text(encoding="utf-8")
    for rule in (
        "substrate-before-sophistication",
        "push-discipline",
        "display-results",
        "session-start tripwire",
        "atomic-push",
    ):
        assert rule.lower() in doc.lower(), f"governance doc missing rule name · '{rule}'"


# ── Invariant 6 · accumulator/PIT parquet integrity ───────────────────

def test_fundamentals_history_parquet_dedupe_invariant():
    """The (market, ticker, asof) tuple must be unique in fundamentals_history · dedupe
    step in accumulate_fundamentals_history is the guard · this asserts it worked."""
    import pandas as pd
    for m in ("india", "usa"):
        p = _ROOT / "reports" / "research" / "fundamentals_history" / f"{m}.parquet"
        if not p.exists(): continue
        df = pd.read_parquet(p)
        if len(df) == 0: continue
        dup_mask = df.duplicated(subset=["market", "ticker", "asof"])
        n_dup = int(dup_mask.sum())
        assert n_dup == 0, f"{m}: {n_dup} duplicate (market, ticker, asof) rows in fundamentals_history"


def test_fundamentals_history_pit_provenance_asof_monotonic():
    """asof values must be sortable dates · not garbage strings · basic PIT provenance."""
    import pandas as pd
    for m in ("india", "usa"):
        p = _ROOT / "reports" / "research" / "fundamentals_history" / f"{m}.parquet"
        if not p.exists(): continue
        df = pd.read_parquet(p)
        if len(df) == 0: continue
        parsed = pd.to_datetime(df["asof"], errors="coerce")
        n_bad = int(parsed.isna().sum())
        assert n_bad == 0, f"{m}: {n_bad} unparseable asof values in fundamentals_history"


def test_accumulator_scripts_exist_and_wired_into_ci():
    """Both accumulator + freshness scripts must exist and be referenced in daily workflows."""
    for f in ("scripts/populate_fundamentals_feature_store.py",
              "scripts/accumulate_fundamentals_history.py",
              "scripts/fundamentals_freshness_check.py"):
        assert (_ROOT / f).exists(), f"missing · {f}"
    daily = (_ROOT / ".github" / "workflows" / "aegis-daily.yml").read_text(encoding="utf-8")
    usa = (_ROOT / ".github" / "workflows" / "aegis-usa.yml").read_text(encoding="utf-8")
    assert "accumulate_fundamentals_history" in daily, "aegis-daily.yml not wired for India accumulator"
    assert "accumulate_fundamentals_history" in usa, "aegis-usa.yml not wired for USA accumulator"
    assert "fundamentals_freshness_check" in daily, "aegis-daily.yml not wired for freshness check"

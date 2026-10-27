"""R3 outcome linkage · the contract that makes evaluation possible at all.

WHY THIS EXISTS
---------------
`shadow.score_outcomes` resolved outcomes through `core.load_pop ->
load_cohort`, which reads a FROZEN research cohort:

    reports/research/mr_prediction_autopsy_<market>_enriched.jsonl
      coverage 2026-08-04 -> 2026-09-08   (725 rows, 26 dates)
    R3 ledger
      coverage 2026-09-08 -> 2026-10-27   (1724 rows, 38 dates)
    key intersection: 0

The outcome source stopped updating the exact day the ledger began, so
`score_outcomes` returned `scored: 0` on every run and
`outcomes_india.jsonl` never existed. **R3 had never scored a single one
of its own predictions.**

`outcome_resolver` computes forward returns from the market's own price
bars instead, so coverage follows the ledger rather than a static file.
First run: 1,724 scored, 5d coverage 81.6%, 10d 63.0%, 20d 37.6%.

These tests pin the properties that make the result trustworthy rather
than merely present.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.research.r3_program import outcome_resolver as orr

ROOT = Path(__file__).resolve().parents[2]


# ── the non-negotiable: predictions are never edited ─────────────────
def test_resolving_never_touches_the_prediction_ledger():
    """A prediction may not be improved after its result is known."""
    from backend.research.r3_program import shadow
    led_p = shadow.ledger_path(ROOT, "india")
    if not led_p.exists():
        pytest.skip("no india ledger")
    before = led_p.read_bytes()
    orr.resolve(ROOT, "india")
    assert led_p.read_bytes() == before, (
        "the prediction ledger changed while scoring outcomes. Predictions "
        "must stay byte-stable once written, or a losing call can be quietly "
        "rewritten after the fact.")


def test_outcomes_live_in_their_own_file():
    p = orr.outcomes_path(ROOT, "india")
    from backend.research.r3_program import shadow
    assert p != shadow.ledger_path(ROOT, "india")
    assert "outcomes_" in p.name


def test_rescoring_appends_nothing():
    """Idempotent · a second pass must not duplicate or re-resolve."""
    p = orr.outcomes_path(ROOT, "india")
    if not p.exists():
        pytest.skip("nothing scored yet")
    before = p.read_bytes()
    r = orr.resolve(ROOT, "india")
    assert r["scored_this_run"] == 0, (
        "re-running scored %d rows · outcomes must be written once"
        % r["scored_this_run"])
    assert p.read_bytes() == before


# ── point-in-time integrity ──────────────────────────────────────────
def _frame(closes, start="2026-01-05"):
    idx = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"close": closes}, index=idx)


def test_forward_return_starts_the_day_AFTER_the_decision():
    """A decision on asof cannot transact at that day's close."""
    df = _frame([100.0, 110.0, 121.0, 121.0, 121.0, 121.0, 121.0])
    asof = df.index[0].strftime("%Y-%m-%d")
    pct, ok = orr.forward_return(df, asof, 1)
    assert ok
    # entry is bar[1]=110 and +1 bar is bar[2]=121 -> +10%, NOT +21%
    assert round(pct, 6) == round(100.0 * (121.0 - 110.0) / 110.0, 6), (
        "the entry bar is the one AFTER asof · including asof's close is "
        "look-ahead")


def test_unmatured_horizon_is_None_never_zero():
    """0.0 for an immature horizon is the easiest way to flatter a result."""
    df = _frame([100.0, 101.0, 102.0])          # only 2 bars after asof
    asof = df.index[0].strftime("%Y-%m-%d")
    pct, ok = orr.forward_return(df, asof, 20)
    assert pct is None and ok is False, (
        "an unmatured 20d horizon returned %r · it must be None with "
        "resolved=False, never 0.0" % pct)


def test_missing_bars_fabricate_nothing():
    pct, ok = orr.forward_return(None, "2026-01-05", 5)
    assert pct is None and ok is False


def test_single_bar_cannot_produce_a_return():
    df = _frame([100.0])
    pct, ok = orr.forward_return(df, df.index[0].strftime("%Y-%m-%d"), 1)
    assert pct is None and ok is False


# ── the real artifact ────────────────────────────────────────────────
def test_every_written_row_carries_a_real_value():
    """Only matured horizons are written · each must hold a number."""
    p = orr.outcomes_path(ROOT, "india")
    if not p.exists():
        pytest.skip("nothing scored yet")
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert rows, "outcomes file is empty"
    for r in rows[:500]:
        assert r.get("resolved") is True, (
            "%s %s h=%s was written while unresolved - an immature horizon "
            "must be ABSENT, not recorded"
            % (r.get("ticker"), r.get("as_of"), r.get("horizon_days")))
        assert isinstance(r.get("fwd_pct"), (int, float)), (
            "%s %s h=%s carries no numeric outcome"
            % (r.get("ticker"), r.get("as_of"), r.get("horizon_days")))
        assert int(r.get("horizon_days")) in orr.HORIZONS


def test_one_outcome_row_per_prediction_horizon_key():
    """Duplicate (as_of, ticker, horizon) would double-weight a decision."""
    p = orr.outcomes_path(ROOT, "india")
    if not p.exists():
        pytest.skip("nothing scored yet")
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    keys = [(r.get("as_of"), r.get("ticker"), r.get("horizon_days"))
            for r in rows]
    assert len(keys) == len(set(keys)), (
        "duplicate (as_of, ticker, horizon) · %d rows, %d unique"
        % (len(keys), len(set(keys))))


def test_an_immature_horizon_can_still_mature_later(tmp_path):
    """The defect that keying on (as_of, ticker) alone would have frozen.

    A first draft skipped any (as_of, ticker) already present, so a row
    written while immature could never fill in: 318 rows had no resolved
    horizon and 758 were resolved at 5d but not 20d - 1,076 of 1,724
    (62%) permanently stuck, with 20d coverage pinned at 37.6% forever.
    """
    import pandas as pd
    led = [{"as_of": "2026-01-06", "ticker": "ZZTEST"}]
    bars_dir = tmp_path / "data" / "raw" / "india"
    bars_dir.mkdir(parents=True)
    out_p = tmp_path / "reports" / "research" / "r3" / "shadow"
    out_p.mkdir(parents=True)

    def write_bars(n):
        idx = pd.bdate_range(start="2026-01-06", periods=n)
        pd.DataFrame({"close": [100.0 + i for i in range(n)]},
                     index=idx).to_parquet(bars_dir / "ZZTEST_D1.parquet")

    write_bars(7)                      # enough for 5d, not 10d or 20d
    orr._cache.clear()
    r1 = orr.resolve(tmp_path, "india", ledger=led)
    assert r1["appended"] == 1, "5d should have matured · got %s" % r1
    assert r1["still_immature"] == 2

    write_bars(12)                     # now 10d matures too
    orr._cache.clear()
    r2 = orr.resolve(tmp_path, "india", ledger=led)
    assert r2["appended"] == 1, (
        "the 10d horizon matured but was not appended - maturity is frozen, "
        "which is exactly the defect per-horizon keying exists to prevent")
    assert r2["already_scored"] == 1

    rows = [json.loads(l) for l in
            (out_p / "outcomes_india.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()]
    keys = [(x["as_of"], x["ticker"], x["horizon_days"]) for x in rows]
    assert sorted(h for _, _, h in keys) == [5, 10]
    assert len(keys) == len(set(keys)), "maturing duplicated a key"


def test_every_outcome_matches_a_real_prediction():
    """No outcome may exist for a decision that was never made."""
    from backend.research.r3_program import shadow
    p = orr.outcomes_path(ROOT, "india")
    if not p.exists():
        pytest.skip("nothing scored yet")
    led = shadow.load_ledger(ROOT, "india")
    lk = {(str(r.get("as_of"))[:10],
           str(r.get("ticker") or "").upper().replace(".NS", ""))
          for r in led}
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    orphan = [(r["as_of"], r["ticker"]) for r in rows
              if (r["as_of"], r["ticker"]) not in lk]
    assert not orphan, "outcomes with no matching prediction: %s" % orphan[:5]


def test_coverage_is_reported_and_declines_with_horizon():
    """Coverage must be a first-class number.

    An evaluation layer that can score nothing must not be able to look
    like a success, and longer horizons necessarily mature less often.
    """
    c = orr.coverage(ROOT, "india")
    if not c.get("outcome_rows"):
        pytest.skip("nothing scored yet")
    for h in orr.HORIZONS:
        assert "coverage_%dd_pct" % h in c
    assert c["resolved_5d"] >= c["resolved_10d"] >= c["resolved_20d"], (
        "coverage must not increase with horizon: 5d=%s 10d=%s 20d=%s"
        % (c["resolved_5d"], c["resolved_10d"], c["resolved_20d"]))


def test_the_frozen_cohort_is_no_longer_the_outcome_source():
    """The defect: a static file that stopped the day the ledger began."""
    src = (ROOT / "backend/research/r3_program/outcome_resolver.py").read_text(
        encoding="utf-8")
    assert "load_cohort" not in src.split('"""', 2)[-1], (
        "the resolver is reading the frozen mr_prediction_autopsy cohort "
        "again · its coverage ended 2026-09-08, the day the ledger started")
    assert "_bars(" in src, "forward returns must come from price bars"


# ── lifecycle integration ────────────────────────────────────────────
def test_shadow_score_uses_the_live_resolver_not_the_frozen_cohort():
    """`shadow.py --score` is the orchestrator's hook (step r3_shadow).

    It previously called score_outcomes(), which resolves through
    core.load_pop -> load_cohort, reading a frozen research cohort that
    covers 2026-08-04..2026-09-08 while the ledger starts 2026-09-08.
    Zero key intersection, so it returned scored:0 forever.
    """
    src = (ROOT / "backend/research/r3_program/shadow.py").read_text(
        encoding="utf-8")
    at = src.find("if a.score:")
    assert at > 0, "the --score hook disappeared from shadow.main()"
    blk = src[at:at + 1600]
    assert "outcome_resolver" in blk, (
        "--score no longer calls outcome_resolver · it would resolve against "
        "the frozen mr_prediction_autopsy cohort again and score nothing")
    # strip comments · the block explains the old path in prose, and a
    # mention is not a call
    code = chr(10).join(ln for ln in blk.splitlines()
                        if not ln.strip().startswith("#"))
    assert "score_outcomes(" not in code, (
        "--score calls score_outcomes() again · it resolves against a frozen "
        "cohort whose coverage ended the day the ledger began")


def test_shadow_can_run_as_a_plain_path():
    """The orchestrator invokes it by path, not with -m.

    Without a repo-root anchor every `from backend...` inside main()
    raises ModuleNotFoundError - which is why r3_shadow sat in the
    orchestrator's optional_failures and outcomes were never written.
    """
    src = (ROOT / "backend/research/r3_program/shadow.py").read_text(
        encoding="utf-8")
    assert "_REPO_ROOT" in src and "sys.path.insert" in src, (
        "shadow.py lost its import anchor · run as a plain path it cannot "
        "import backend.* and --score crashes")
    root = (ROOT / "backend/research/r3_program/shadow.py").resolve().parents[3]
    assert (root / "backend").is_dir(), "anchor resolves to the wrong depth"


def test_outcome_artifacts_are_declared_by_the_orchestrator_step():
    """Undeclared outputs are invisible to staleness detection."""
    src = (ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    at = src.find('"name":       "r3_shadow"')
    assert at > 0, "r3_shadow step missing"
    nxt = src.find('"name":', at + 20)
    blk = src[at:nxt if nxt > at else at + 2500]
    for m in ("india", "usa"):
        assert "outcomes_%s.jsonl" % m in blk, (
            "outcomes_%s.jsonl is written by --score but not declared" % m)

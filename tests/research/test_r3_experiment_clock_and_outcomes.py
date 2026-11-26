"""B7 (clock start) and C4 (outcome isolation) · isolated fixtures only.

B7 · the 90-day clock begins at the first SUCCESSFULLY PERSISTED eligible
prospective decision. The protocol previously carried only a planned
window, which left the actual start event undefined - so "the clock has
started" was an assertion rather than a recorded fact.

C4 · outcome_resolver.resolve() hardcodes its destination to
reports/research/r3/shadow/outcomes_<market>.jsonl (outcome_resolver.py
line ~155) and accepts a `ledger=` argument. Wiring the experiment
through it would therefore append experiment outcomes into the SHADOW
track's file, merging two unrelated decision populations. The regression
test here is a byte comparison of the shadow ledger across an experiment
resolution - asserted on behaviour, because a source scan for the string
"shadow" matches the docstring that explains the rule and would pass on
broken code.

Every fixture builds its own tree under tmp_path. No test here reads or
writes a live ledger or outcomes file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.research.r3_program import shadow_recommender as sr
from backend.research.r3_program import experiment_outcomes as eo

REPO = Path(__file__).resolve().parents[2]


# ── fixtures ─────────────────────────────────────────────────────────
def _snapshot(root: Path, market: str, asof: str, n: int = 60):
    df = pd.DataFrame({
        "ticker": ["T%03d" % i for i in range(n)],
        "ensemble_score": [float(n - i) for i in range(n)],
    })
    p = root / "history" / market / asof / "r2_scores.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def _mature_bars(root: Path, market: str, tickers, asof: str,
                 periods: int = 40):
    """Enough bars after asof that all three horizons resolve."""
    idx = pd.bdate_range(start=pd.Timestamp(asof), periods=periods)
    for i, t in enumerate(tickers):
        df = pd.DataFrame(
            {"close": [100.0 + j * (1 + i % 3) for j in range(periods)]},
            index=idx)
        p = root / (sr.BARS[market] % t)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p)


def _shadow_outcomes(root: Path, market: str, n: int = 3) -> Path:
    """A pre-existing SHADOW outcomes ledger that must not be touched."""
    p = (root / "reports" / "research" / "r3" / "shadow"
         / ("outcomes_%s.jsonl" % market))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({
                "as_of": "2026-09-0%d" % (i + 1), "ticker": "SHADOW%d" % i,
                "market": market, "horizon_days": 5, "fwd_pct": 1.0,
                "resolved": True,
                "schema_version": "aegis.r3.outcome_resolver.v1"}) + "\n")
    return p


# ══ B7 · clock start ═════════════════════════════════════════════════
def test_no_clock_start_before_anything_is_persisted(tmp_path):
    assert sr.read_clock_start(tmp_path, "india") is None


def test_backtest_only_persistence_does_not_start_the_clock(tmp_path):
    """A backfilled date is not a forward observation."""
    _snapshot(tmp_path, "india", "2026-01-05")       # long past
    rep = sr.run(tmp_path, "india")
    assert rep["recorded_this_run"] > 0
    assert rep["prospective_rows"] == 0
    assert rep["clock_started"] is False
    assert sr.read_clock_start(tmp_path, "india") is None, (
        "the clock started on backtest rows · those outcomes already "
        "existed when they were recorded")


def test_first_prospective_persistence_starts_the_clock(tmp_path):
    import datetime as _dt
    today = _dt.date.today().isoformat()
    _snapshot(tmp_path, "india", today)
    rep = sr.run(tmp_path, "india")
    assert rep["prospective_rows"] > 0
    assert rep["clock_started"] is True
    ev = sr.read_clock_start(tmp_path, "india")
    assert ev is not None
    assert ev["event"] == "PROSPECTIVE_EXPERIMENT_START"
    assert ev["observed_start_as_of"] == today
    assert ev["observed_start_utc"] == rep["clock_start_utc"]
    assert ev["first_decision_id"], "no decision identity on the event"
    assert ev["immutable"] is True
    assert ev["protocol_version"] and ev["protocol_hash_at_start"]


def test_the_clock_start_is_write_once(tmp_path):
    """Re-runs, and later dates, must not move the start event."""
    import datetime as _dt
    today = _dt.date.today()
    _snapshot(tmp_path, "india", today.isoformat())
    sr.run(tmp_path, "india")
    p = sr.clock_start_path(tmp_path, "india")
    first = p.read_bytes()

    sr.run(tmp_path, "india")                       # idempotent re-run
    assert p.read_bytes() == first

    _snapshot(tmp_path, "india",
              (today + _dt.timedelta(days=1)).isoformat())
    sr.run(tmp_path, "india")
    assert p.read_bytes() == first, (
        "a later prospective date moved the clock start · the window would "
        "slide forward indefinitely")


def test_start_outside_the_planned_window_is_flagged_not_reconciled(tmp_path):
    """Preregistration must never be silently rewritten to agree."""
    from backend.research.r3_program import experiment_protocol as ep
    rows = [{
        "evidence_segment": "prospective",
        "as_of": "2027-06-01",                      # far past planned end
        "decision_utc": "2027-06-01T09:00:00+00:00",
        "decision_id": "r3x_fake", "ticker": "ZZZ",
        "engine_version": sr.ENGINE_VERSION,
    }]
    ev = sr.record_clock_start(tmp_path, "india", rows)
    assert ev["observed_start_within_planned_window"] is False
    assert ev["discrepancy"] and "amendment" in ev["discrepancy"]
    # preregistration itself is untouched
    assert ep.PREREGISTERED_ON == "2026-10-28"
    assert ev["planned_window"]["start"] == "2026-10-28"


def test_clock_event_records_the_decision_it_started_from(tmp_path):
    import datetime as _dt
    today = _dt.date.today().isoformat()
    _snapshot(tmp_path, "india", today)
    sr.run(tmp_path, "india")
    ev = sr.read_clock_start(tmp_path, "india")
    led = sr._read_jsonl(sr.ledger_path(tmp_path, "india"))
    ids = {r["decision_id"] for r in led}
    assert ev["first_decision_id"] in ids, (
        "the clock cites a decision that is not in the ledger")


# ══ C4 · outcome isolation ═══════════════════════════════════════════
def test_experiment_resolution_never_touches_the_shadow_ledger(tmp_path):
    """THE regression test for C4 · byte comparison, not a source scan."""
    shadow_p = _shadow_outcomes(tmp_path, "india")
    before = shadow_p.read_bytes()

    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    rep = eo.resolve(tmp_path, "india")

    assert rep["resolved_this_run"] > 0, "nothing resolved · test is vacuous"
    assert shadow_p.read_bytes() == before, (
        "experiment resolution mutated the SHADOW outcomes ledger · two "
        "unrelated decision populations have been merged")


def test_experiment_outcomes_live_in_their_own_file(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    p = eo.outcomes_path(tmp_path, "india")
    assert p.exists()
    assert "experiment" in str(p).replace("\\", "/")
    assert "shadow" not in str(p).replace("\\", "/")


def test_resolution_does_not_rewrite_the_decision_ledger(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    led = sr.ledger_path(tmp_path, "india")
    before = led.read_bytes()
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    assert led.read_bytes() == before, (
        "a decision was edited after its outcome became known")


def test_outcomes_are_keyed_by_decision_id_and_horizon(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    rows = sr._read_jsonl(eo.outcomes_path(tmp_path, "india"))
    keys = [(r["decision_id"], r["horizon_days"]) for r in rows]
    assert len(keys) == len(set(keys)), "duplicate (decision_id, horizon)"
    for r in rows:
        assert r["decision_id"].startswith("r3x_")
        assert r["horizon_days"] in eo.HORIZONS


def test_resolution_is_idempotent(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    first = eo.resolve(tmp_path, "india")
    p = eo.outcomes_path(tmp_path, "india")
    blob = p.read_bytes()
    second = eo.resolve(tmp_path, "india")
    assert second["resolved_this_run"] == 0, (
        "re-resolution appended %d duplicate rows"
        % second["resolved_this_run"])
    assert p.read_bytes() == blob
    assert second["outcomes_total"] == first["outcomes_total"]


def test_an_immature_horizon_is_absent_not_zero(tmp_path):
    """Only 8 bars exist · 5d resolves, 10d and 20d must not."""
    _snapshot(tmp_path, "india", "2026-01-05", n=60)
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05", periods=8)
    eo.resolve(tmp_path, "india")
    rows = sr._read_jsonl(eo.outcomes_path(tmp_path, "india"))
    hs = {r["horizon_days"] for r in rows}
    assert 5 in hs, "5d should have matured with 8 bars"
    assert 20 not in hs, (
        "a 20-day horizon resolved from 8 bars · it has been invented")
    assert all(r["fwd_pct"] is not None for r in rows)
    assert all(r["resolved"] is True for r in rows)


def test_missing_bars_are_counted_not_imputed(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    rep = eo.resolve(tmp_path, "india")          # no bars written at all
    assert rep["resolved_this_run"] == 0
    assert rep["no_bars"] > 0, "missing bars were not reported"
    assert not eo.outcomes_path(tmp_path, "india").exists() or \
        sr._read_jsonl(eo.outcomes_path(tmp_path, "india")) == []


def test_evidence_segment_is_copied_from_the_decision(tmp_path):
    """Recomputing it at resolution time would reclassify history."""
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    rows = sr._read_jsonl(eo.outcomes_path(tmp_path, "india"))
    assert rows
    assert all(r["evidence_segment"] == "backtest" for r in rows), (
        "a January decision resolved today was labelled prospective")


def test_coverage_reports_segments_separately(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    c = eo.coverage(tmp_path, "india")
    assert "prospective" in c and "backtest" in c
    assert c["backtest"]["decisions"] > 0
    assert c["prospective"]["decisions"] == 0
    assert "resolvable is not validated" in c["note"]


# ══ added criteria · engine versions, concurrency, corrections ══════
def test_different_engine_versions_do_not_collide(tmp_path):
    """A policy change is a new decision, not an overwrite."""
    a = sr.decision_id("india", "2026-10-01", "ABC", "R3_BASE_v1")
    b = sr.decision_id("india", "2026-10-01", "ABC", "R3_BASE_v2")
    assert a != b
    rows_a = [{"decision_id": a, "as_of": "2026-01-05", "ticker": "ZZZ",
               "evidence_segment": "backtest", "action": "TAKE",
               "engine_version": "R3_BASE_v1"}]
    rows_b = [{"decision_id": b, "as_of": "2026-01-05", "ticker": "ZZZ",
               "evidence_segment": "backtest", "action": "AVOID",
               "engine_version": "R3_BASE_v2"}]
    _mature_bars(tmp_path, "india", ["ZZZ"], "2026-01-05")
    eo.resolve(tmp_path, "india", decisions=rows_a)
    eo.resolve(tmp_path, "india", decisions=rows_b)
    out = sr._read_jsonl(eo.outcomes_path(tmp_path, "india"))
    vers = {r["engine_version"] for r in out}
    assert vers == {"R3_BASE_v1", "R3_BASE_v2"}, (
        "one engine version overwrote the other: %s" % vers)
    keys = [(r["decision_id"], r["horizon_days"]) for r in out]
    assert len(keys) == len(set(keys))


def test_missing_or_conflicting_decision_reference_is_rejected(tmp_path):
    bad = [{"as_of": "2026-01-05", "ticker": "X"},        # no decision_id
           {"decision_id": "d1"}]                        # no as_of/ticker
    rep = eo.resolve(tmp_path, "india", decisions=bad)
    reasons = {r["reason"] for r in rep["rejected"]}
    assert reasons == {"MISSING_DECISION_ID",
                       "INCOMPLETE_DECISION_REFERENCE"}
    assert rep["n_rejected"] == 2
    assert rep["resolved_this_run"] == 0


def test_unresolved_keys_carry_an_explicit_reason(tmp_path):
    """Never zero · and never silently absent from the report either."""
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    rep = eo.resolve(tmp_path, "india")           # no bars at all
    assert rep["n_unresolved"] > 0
    assert "NO_PRICE_SERIES" in rep["unresolved_by_reason"]
    assert rep["resolved_this_run"] == 0

    # now give short bars · the reason must change, not vanish
    eo.reset_cache()
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05", periods=8)
    rep2 = eo.resolve(tmp_path, "india")
    assert "INSUFFICIENT_FUTURE_BARS" in rep2["unresolved_by_reason"]


def test_repeated_initialisation_cannot_change_the_clock(tmp_path):
    """Second caller with DIFFERENT rows must get the first event back."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    _snapshot(tmp_path, "india", today)
    sr.run(tmp_path, "india")
    p = sr.clock_start_path(tmp_path, "india")
    first = p.read_bytes()
    original_id = json.loads(first)["first_decision_id"]

    ev = sr.record_clock_start(tmp_path, "india", [{
        "evidence_segment": "prospective", "as_of": "2027-01-01",
        "decision_utc": "2027-01-01T00:00:00+00:00",
        "decision_id": "r3x_intruder", "ticker": "QQQ",
        "engine_version": "OTHER_v9"}])
    assert p.read_bytes() == first, "the clock start was overwritten"
    assert ev["first_decision_id"] == original_id, (
        "the second caller got its own event rather than the recorded one")


def test_clock_is_stamped_from_an_already_persisted_ledger(tmp_path):
    """The hole this closes · stamping only from newly-written rows.

    The real India ledger had 228 prospective rows persisted before the
    clock feature existed, so every later run saw new=[] and the start
    event was never recorded. The ledger itself carries each row's
    decision_utc, which IS the persistence time.
    """
    import datetime as _dt
    today = _dt.date.today().isoformat()
    _snapshot(tmp_path, "india", today)
    sr.run(tmp_path, "india")
    p = sr.clock_start_path(tmp_path, "india")
    assert p.exists()
    p.unlink()                              # simulate the pre-feature state

    rep = sr.run(tmp_path, "india")         # records 0 new rows
    assert rep["recorded_this_run"] == 0
    assert rep["clock_started"] is True, (
        "a ledger with prospective rows left the clock unstamped")
    ev = sr.read_clock_start(tmp_path, "india")
    led = sr._read_jsonl(sr.ledger_path(tmp_path, "india"))
    pros = [r for r in led if r["evidence_segment"] == "prospective"]
    assert ev["observed_start_utc"] == min(r["decision_utc"] for r in pros)


def test_clock_start_leaves_no_temp_files(tmp_path):
    import datetime as _dt
    _snapshot(tmp_path, "india", _dt.date.today().isoformat())
    sr.run(tmp_path, "india")
    d = sr.clock_start_path(tmp_path, "india").parent
    assert not list(d.glob("*.tmp*")), (
        "a partial clock-start file was left behind: %s"
        % list(d.glob("*.tmp*")))


def test_a_correction_supersedes_without_editing_history(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05", n=60)
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    p = eo.outcomes_path(tmp_path, "india")
    rows = sr._read_jsonl(p)
    target = rows[0]
    n_before, orig = len(rows), target["fwd_pct"]

    eo.append_correction(tmp_path, "india", target["decision_id"],
                         target["horizon_days"], 42.0,
                         "vendor restated the split adjustment")

    rows2 = sr._read_jsonl(p)
    assert len(rows2) == n_before + 1, "a correction replaced a row"
    assert any(r["fwd_pct"] == orig for r in rows2), (
        "the original measurement was destroyed · it must stay auditable")
    eff = eo.latest_by_key(rows2)[(target["decision_id"],
                                   target["horizon_days"])]
    assert eff["fwd_pct"] == 42.0
    assert eff["supersedes"] == target["resolved_utc"]
    assert eff["correction_reason"]
    assert eff["is_correction"] is True


def test_a_correction_without_a_reason_is_refused(tmp_path):
    _snapshot(tmp_path, "india", "2026-01-05")
    sr.run(tmp_path, "india")
    _mature_bars(tmp_path, "india", ["T%03d" % i for i in range(60)],
                 "2026-01-05")
    eo.resolve(tmp_path, "india")
    rows = sr._read_jsonl(eo.outcomes_path(tmp_path, "india"))
    with pytest.raises(ValueError):
        eo.append_correction(tmp_path, "india", rows[0]["decision_id"],
                             rows[0]["horizon_days"], 1.0, "")
    with pytest.raises(ValueError):
        eo.append_correction(tmp_path, "india", "r3x_nonexistent", 5, 1.0,
                             "reason given but key does not exist")


def test_correction_path_is_documented_on_every_report(tmp_path):
    rep = eo.resolve(tmp_path, "india", decisions=[
        {"decision_id": "d", "as_of": "2026-01-05", "ticker": "ZZZ",
         "evidence_segment": "backtest"}])
    cp = rep["correction_path"]
    assert "supersedes" in cp
    assert "correction_reason" in cp
    assert "Nothing is ever edited or deleted" in cp, (
        "the correction contract no longer states that history is "
        "preserved · an in-place restatement would leave no trace")


@pytest.mark.parametrize("mod_name", ["experiment_outcomes",
                                      "outcome_resolver"])
def test_bar_cache_is_keyed_by_root(tmp_path, mod_name):
    """Two roots in one process must not share price frames.

    The cache was keyed (market, ticker). A test tree then inherited bars
    from an earlier test tree, and 8 bars resolved a 20-day horizon. The
    same collision would serve one repository's prices for another's
    tickers in any process that handled both.
    """
    import importlib
    mod = importlib.import_module(
        "backend.research.r3_program.%s" % mod_name)
    a, b = tmp_path / "A", tmp_path / "B"
    # root A gets 40 bars · root B gets only 6
    _mature_bars(a, "india", ["ZZZ"], "2026-01-05", periods=40)
    _mature_bars(b, "india", ["ZZZ"], "2026-01-05", periods=6)

    da = mod._bars(a, "india", "ZZZ")
    db = mod._bars(b, "india", "ZZZ")
    assert da is not None and db is not None
    assert len(da) == 40 and len(db) == 6, (
        "root A saw %d bars and root B saw %d · the cache is serving one "
        "root's prices for the other's" % (len(da), len(db)))

    # and the 20d horizon must be immature in B even though A matured it
    from backend.research.r3_program.outcome_resolver import forward_return
    _, ok_a = forward_return(da, "2026-01-05", 20)
    _, ok_b = forward_return(db, "2026-01-05", 20)
    assert ok_a is True and ok_b is False


def test_experiment_module_does_not_import_the_resolver_writer():
    """It may reuse forward_return · it must not reuse resolve()."""
    import ast
    src = (REPO / "backend" / "research" / "r3_program"
           / "experiment_outcomes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                imported.add("%s.%s" % (node.module, a.name))
    assert any(n.endswith(".forward_return") for n in imported), (
        "forward_return is no longer reused · the pure function is the one "
        "thing worth sharing")
    assert not any(n.endswith("outcome_resolver.resolve") for n in imported), (
        "resolve() is imported · its destination is hardcoded to the shadow "
        "outcomes path and it would merge the two tracks")
    assert not any(n.endswith("outcome_resolver.outcomes_path")
                   for n in imported)

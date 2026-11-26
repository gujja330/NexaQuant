"""The R3 experimental track must be honest, immutable and inert.

CEO 2026-10-28 · This is the first R3 component that emits something
other than ABSTAIN, so the things that could go quietly wrong are:

  * a decision-time field computed from a future bar
  * a re-run silently rewriting an earlier decision
  * a thin cross-section being deciled anyway
  * a missing snapshot being guessed around instead of refused
  * null probabilities drifting to 0.0 and reading as confident
  * the experiment touching anything R2 owns

Every fixture below builds its own tree under tmp_path. Nothing here
reads or writes the live ledger, the live outcomes file, or any real
artifact - that rule exists because an earlier session appended 2,812
duplicate rows to the live outcomes file by running a mutation against
it.

Each guard is tested in BOTH directions: the valid case passes and a
deliberately invalid case fails. A guard that cannot fail is worse than
no guard, because it reads as protection.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.research.r3_program import shadow_recommender as sr

REPO = Path(__file__).resolve().parents[2]


# ── fixtures · isolated trees only ───────────────────────────────────
def _snapshot(root: Path, market: str, asof: str, n: int = 60,
              tickers=None) -> Path:
    """A sealed r2_scores snapshot with a clean monotone score."""
    tickers = tickers or ["T%03d" % i for i in range(n)]
    df = pd.DataFrame({
        "ticker": tickers,
        # descending so T000 is best · makes rank assertions readable
        "ensemble_score": [float(len(tickers) - i) for i in
                           range(len(tickers))],
        "action": ["HOLD"] * len(tickers),
        "calibrated_confidence": [0.5] * len(tickers),
    })
    p = root / "history" / market / asof / "r2_scores.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    return p


def _bars(root: Path, market: str, ticker: str, asof: str,
          close_before: float, close_after: float):
    """Bars straddling asof · `close_after` is the future we must not see."""
    idx = pd.bdate_range(end=pd.Timestamp(asof), periods=3).append(
        pd.bdate_range(start=pd.Timestamp(asof), periods=6)[1:])
    vals = [close_before] * 3 + [close_after] * 5
    df = pd.DataFrame({"close": vals}, index=idx)
    rel = sr.BARS[market] % ticker
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    return p


# ── identity + immutability ──────────────────────────────────────────
def test_decision_id_is_deterministic():
    a = sr.decision_id("india", "2026-10-01", "ABC")
    b = sr.decision_id("INDIA", "2026-10-01", " abc ")
    assert a == b, "identity must be stable under case/whitespace"
    assert a != sr.decision_id("india", "2026-10-02", "ABC")
    assert a != sr.decision_id("usa", "2026-10-01", "ABC")


def test_a_different_engine_version_is_a_different_decision():
    """Otherwise a new policy silently overwrites the old one's history."""
    a = sr.decision_id("india", "2026-10-01", "ABC", "R3_BASE_v1")
    b = sr.decision_id("india", "2026-10-01", "ABC", "R3_BASE_v2")
    assert a != b


def test_decision_id_tracks_the_engine_version_at_call_time(monkeypatch):
    """The default argument must not freeze the version at import.

    `engine_version=ENGINE_VERSION` as a default is bound ONCE when the
    module loads. The recorded engine_version field reads the module
    attribute at call time, so after a policy bump a row claimed v2 while
    its decision_id was still hashed from v1 - identity and the version
    it asserts came from different places.
    """
    before = sr.decision_id("india", "2026-10-01", "ABC")
    monkeypatch.setattr(sr, "ENGINE_VERSION", "R3_BUMPED_v9")
    after = sr.decision_id("india", "2026-10-01", "ABC")
    assert after != before, (
        "decision_id ignored the bumped ENGINE_VERSION · it is frozen at "
        "import, so a new policy would silently reuse the old identity")
    assert after == sr.decision_id("india", "2026-10-01", "ABC",
                                   "R3_BUMPED_v9")


def test_recorded_engine_version_matches_the_hashed_one(tmp_path,
                                                        monkeypatch):
    """Consistency · the row's version and its id must agree."""
    monkeypatch.setattr(sr, "ENGINE_VERSION", "R3_BUMPED_v9")
    _snapshot(tmp_path, "india", "2026-10-01", n=60)
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    assert res["records"]
    for r in res["records"][:5]:
        assert r["engine_version"] == "R3_BUMPED_v9"
        assert r["decision_id"] == sr.decision_id(
            "india", "2026-10-01", r["ticker"], "R3_BUMPED_v9"), (
            "%s claims version %s but its id hashes a different one"
            % (r["ticker"], r["engine_version"]))


def test_rerunning_a_date_records_nothing_new(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01")
    first = sr.run(tmp_path, "india")
    assert first["recorded_this_run"] > 0
    second = sr.run(tmp_path, "india")
    assert second["recorded_this_run"] == 0, (
        "a re-run wrote %d more rows · the ledger is not idempotent"
        % second["recorded_this_run"])
    assert second["ledger_total"] == first["ledger_total"]


def test_history_is_append_only_never_edited(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01")
    sr.run(tmp_path, "india")
    p = sr.ledger_path(tmp_path, "india")
    before = p.read_bytes()
    _snapshot(tmp_path, "india", "2026-10-02")
    sr.run(tmp_path, "india")
    after = p.read_bytes()
    assert after.startswith(before), (
        "the existing ledger prefix changed · earlier decisions were "
        "rewritten rather than appended to")


# ── no future leakage ────────────────────────────────────────────────
def test_reference_price_never_uses_a_bar_after_asof(tmp_path):
    """The decisive leakage test.

    Bars are flat at 100 up to and including asof, then jump to 999.
    A reference price of 999 would mean the future reached a
    decision-time field.
    """
    asof = "2026-10-01"
    _bars(tmp_path, "india", "ABC", asof, close_before=100.0,
          close_after=999.0)
    px, pxd = sr._reference_price(tmp_path, "india", "ABC", asof)
    assert px == 100.0, (
        "reference price %s came from a bar after %s · the future leaked "
        "into a decision-time field" % (px, asof))
    assert pxd <= asof


def test_leakage_guard_can_fail(tmp_path):
    """Prove the test above would catch a leak rather than always pass."""
    asof = "2026-10-01"
    _bars(tmp_path, "india", "ABC", asof, close_before=100.0,
          close_after=999.0)
    d = pd.read_parquet(tmp_path / (sr.BARS["india"] % "ABC"))
    d.index = pd.to_datetime(d.index)
    future = d[d.index > pd.Timestamp(asof)]["close"].iloc[0]
    assert future == 999.0, "fixture is wrong · there is no future to leak"
    px, _ = sr._reference_price(tmp_path, "india", "ABC", asof)
    assert px != future


def test_a_missing_bar_is_flagged_not_invented(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01")
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    acted = [r for r in res["records"] if r["action"] in ("TAKE", "AVOID")]
    assert acted
    for r in acted:
        assert r["reference_price"] is None
        assert "NO_REFERENCE_PRICE" in r["risk_flags"], (
            "no bars exist for %s yet no risk flag was raised" % r["ticker"])


# ── the policy ───────────────────────────────────────────────────────
def test_deciles_match_the_configured_rates(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01", n=100)
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    from collections import Counter
    c = Counter(r["action"] for r in res["records"])
    assert c["TAKE"] == 10 and c["AVOID"] == 10, (
        "100 names at 10%% deciles gave TAKE=%d AVOID=%d"
        % (c["TAKE"], c["AVOID"]))
    assert c["ABSTAIN"] == 80


def test_take_goes_to_the_best_scores_not_the_worst(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01", n=100)
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    takes = [r for r in res["records"] if r["action"] == "TAKE"]
    avoids = [r for r in res["records"] if r["action"] == "AVOID"]
    assert min(r["rationale"]["score"] for r in takes) > \
        max(r["rationale"]["score"] for r in avoids), (
        "the rule is inverted · TAKE is being assigned to low scores")


def test_a_thin_universe_abstains_rather_than_deciling(tmp_path):
    """A decile of a 5-name cross-section is noise wearing a rule."""
    _snapshot(tmp_path, "india", "2026-10-01", n=5)
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    assert res["refused"] == "UNIVERSE_BELOW_MINIMUM"
    assert res["records"], "it must still RECORD the abstention"
    assert all(r["action"] == "ABSTAIN" for r in res["records"])
    assert all("UNIVERSE_BELOW_MINIMUM" in (r["abstention_reason"] or "")
               for r in res["records"])


def test_a_missing_snapshot_is_refused_not_guessed(tmp_path):
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    assert res["refused"] == "SNAPSHOT_MISSING_OR_MALFORMED"
    assert res["records"] == []


def test_a_malformed_snapshot_is_refused(tmp_path):
    p = tmp_path / "history" / "india" / "2026-10-01" / "r2_scores.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"nonsense": [1, 2, 3]}).to_parquet(p)
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    assert res["refused"] == "SNAPSHOT_MISSING_OR_MALFORMED"


def test_probabilities_are_null_never_zero(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01")
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    for r in res["records"]:
        for k in ("take_probability", "avoid_probability",
                  "abstain_probability"):
            assert r[k] is None, (
                "%s is %r · a rank rule produces an ordering, not a "
                "calibrated probability, and 0.0 would read downstream as "
                "a confident forecast" % (k, r[k]))


def test_records_are_labelled_experimental_and_not_a_specialist(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01")
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    for r in res["records"]:
        assert r["output_kind"] == "EXPERIMENTAL_BASELINE"
        assert r["specialist_id"] is None, (
            "this must never be attributable to a specialist · none of the "
            "11 has executable logic")
        assert "UNVALIDATED" in r["validation_status"]
        assert r["production_impact"].startswith("NONE")


# ── isolation from production ────────────────────────────────────────
def _imported_modules(path: Path) -> set:
    """Real import statements only · parsed, not grepped.

    A substring scan of the source also matches the docstring that
    EXPLAINS the isolation rule, which would make this guard fail on
    correct code and teach everyone to ignore it.
    """
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_module_imports_nothing_from_production():
    mods = _imported_modules(REPO / "backend" / "research" / "r3_program"
                             / "shadow_recommender.py")
    banned = ("backend.delivery", "backend.recommendation",
              "backend.execution", "backend.portfolio")
    hits = [m for m in mods
            if any(m == b or m.startswith(b + ".") for b in banned)
            or "telegram" in m.lower()]
    assert not hits, (
        "shadow_recommender imports %s · isolation must be structural, "
        "not a promise" % hits)


def test_the_import_guard_can_actually_fail(tmp_path):
    """Prove the AST scan detects a banned import when one exists."""
    p = tmp_path / "leaky.py"
    p.write_text("from backend.delivery import telegram_send\nx = 1\n",
                 encoding="utf-8")
    mods = _imported_modules(p)
    assert "backend.delivery" in mods, (
        "the AST scan missed a real import · every isolation assertion "
        "above would pass vacuously")


def test_running_the_experiment_writes_only_under_its_own_directory(tmp_path):
    """Strongest isolation evidence · nothing R2 owns is touched."""
    _snapshot(tmp_path, "india", "2026-10-01")
    # a decoy artifact in the shape of something R2 owns
    r2 = tmp_path / "reports" / "context" / "canonical_lifecycle_india.json"
    r2.parent.mkdir(parents=True, exist_ok=True)
    r2.write_text(json.dumps({"current": [{"ticker": "ZZZ"}]}),
                  encoding="utf-8")
    before = r2.read_bytes()

    sr.run(tmp_path, "india")

    assert r2.read_bytes() == before, "the experiment modified an R2 artifact"
    written = {str(p.relative_to(tmp_path)).replace("\\", "/")
               for p in tmp_path.rglob("*") if p.is_file()}
    created = {w for w in written
               if w.startswith("reports/") and "r2_scores" not in w}
    stray = {w for w in created
             if not w.startswith("reports/research/r3/experiment/")
             and w != "reports/context/canonical_lifecycle_india.json"}
    assert not stray, (
        "the experiment wrote outside its own directory: %s" % sorted(stray))


# ── coverage observability ───────────────────────────────────────────
def test_zero_coverage_cannot_look_like_a_healthy_run(tmp_path):
    """A run that records nothing must leave a distinguishable trace."""
    sr.run(tmp_path, "india")          # no snapshots at all
    cov = sr.coverage_path(tmp_path, "india")
    assert cov.exists(), "a zero-coverage run left no trace"
    rows = [json.loads(l) for l in
            cov.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows[-1]["recorded_this_run"] == 0
    assert rows[-1]["ledger_total"] == 0
    assert rows[-1]["evidence_class"] == "EXPLORATORY"


def test_evidence_class_uses_dates_not_rows():
    assert sr.evidence_class(19) == "EXPLORATORY"
    assert sr.evidence_class(20) == "CONFIRMATORY-ELIGIBLE"
    assert sr.MIN_DATES_CONFIRMATORY == 20


def test_coverage_accumulates_across_runs(tmp_path):
    _snapshot(tmp_path, "india", "2026-10-01")
    sr.run(tmp_path, "india")
    sr.run(tmp_path, "india")
    rows = [json.loads(l) for l in sr.coverage_path(tmp_path, "india")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2, (
        "coverage must be a history · overwriting it hides a run that "
        "recorded nothing")


# ── outcome resolution · reuse, per-horizon, idempotent ──────────────
def test_outcome_resolver_matures_each_horizon_independently(tmp_path):
    """5d resolves while 20d is still immature · and never as 0.0."""
    from backend.research.r3_program import outcome_resolver as orr
    idx = pd.bdate_range(start="2026-01-05", periods=9)
    df = pd.DataFrame({"close": [100.0, 100.0, 101.0, 102.0, 103.0,
                                 104.0, 105.0, 106.0, 107.0]}, index=idx)
    asof = idx[0].strftime("%Y-%m-%d")
    v5, ok5 = orr.forward_return(df, asof, 5)
    v20, ok20 = orr.forward_return(df, asof, 20)
    assert ok5 and v5 is not None
    assert not ok20 and v20 is None, (
        "an immature horizon returned %r · recording it as a number, and "
        "especially as 0.0, manufactures a flattering result" % (v20,))


def test_outcome_keys_are_per_horizon():
    from backend.research.r3_program import outcome_resolver as orr
    assert tuple(orr.HORIZONS) == (5, 10, 20)
    assert tuple(sr.HORIZONS) == tuple(orr.HORIZONS), (
        "the experiment and the resolver disagree on horizons")


# ── preregistered protocol ───────────────────────────────────────────
def test_segment_is_decided_by_whether_the_outcome_already_existed():
    """The single most important rule in the protocol.

    A snapshot sealed this morning has no 5/10/20-day outcome yet, so
    recording it today is prospective. One from six weeks ago has all
    three resolved, so recording it today is a backtest however
    point-in-time its inputs were. Letting the second count as forward
    evidence is exactly how the withdrawn USA meta-label happened.
    """
    from backend.research.r3_program import experiment_protocol as ep
    rec = "2026-10-28"
    assert sr.evidence_segment("2026-10-28", rec) == "prospective"
    assert sr.evidence_segment("2026-10-29", rec) == "prospective"
    assert sr.evidence_segment("2026-10-27", rec) == "backtest"
    assert sr.evidence_segment("2026-09-15", rec) == "backtest"
    assert sr.evidence_segment("not-a-date", rec) == "unknown"
    # one definition, not two that can drift
    assert ep.segment_of("2026-09-15", rec) == "backtest"
    assert ep.segment_of("2026-10-28", rec) == "prospective"


def test_segment_is_frozen_into_the_record_not_recomputed(tmp_path):
    """Otherwise yesterday's backtest row becomes prospective tomorrow."""
    _snapshot(tmp_path, "india", "2026-01-05")
    res = sr.decide_date(tmp_path, "india", "2026-01-05")
    assert res["records"]
    for r in res["records"]:
        assert r["evidence_segment"] == "backtest", (
            "a January snapshot recorded today must be backtest")
        assert "evidence_segment" in r


def test_backfilled_dates_cannot_be_counted_as_prospective():
    """Every sealed date that exists right now is backtest."""
    from backend.research.r3_program import experiment_protocol as ep
    import datetime as _dt
    today = _dt.date.today().isoformat()
    for market in ("india", "usa"):
        for d in sr.snapshot_dates(REPO, market):
            if d < today:
                assert ep.segment_of(d, today) == "backtest", (
                    "%s %s would count as forward evidence" % (market, d))


def test_pooling_the_two_segments_is_explicitly_forbidden():
    from backend.research.r3_program import experiment_protocol as ep
    assert ep.PROTOCOL["segments"]["pooling"].startswith("FORBIDDEN")


def test_missing_score_is_recorded_as_abstain_not_dropped(tmp_path):
    """Dropping it would shrink the universe and the denominator silently."""
    df = pd.DataFrame({
        "ticker": ["T%03d" % i for i in range(60)] + ["NOSCORE"],
        "ensemble_score": [float(60 - i) for i in range(60)] + [None]})
    c = sr.classify(df)
    assert "NOSCORE" in c, (
        "an unscored candidate vanished · it is then indistinguishable "
        "from a name that was never a candidate")
    assert c["NOSCORE"]["action"] == "ABSTAIN"
    assert c["NOSCORE"]["reason_code"] == "NO_SCORE"
    assert c["NOSCORE"]["score"] is None
    # the denominator counts scored names only
    assert c["T000"]["n"] == 60


def test_a_tie_at_the_boundary_abstains_rather_than_picking_one():
    """Two identical scores give no basis to take one and not the other."""
    n = 60
    df = pd.DataFrame({"ticker": ["T%03d" % i for i in range(n)],
                       "ensemble_score": [float(n - i) for i in range(n)]})
    df.loc[4:6, "ensemble_score"] = 55.0        # 3-way tie across the cut
    c = sr.classify(df)
    tied = [k for k, v in c.items()
            if v.get("reason_code") == "TIE_AT_BOUNDARY"]
    assert set(tied) == {"T004", "T005", "T006"}, (
        "tied names at the cut were not abstained: %s" % tied)
    assert all(c[t]["action"] == "ABSTAIN" for t in tied)


def test_tie_handling_is_order_independent():
    """Shuffle the rows · the same names must get the same actions."""
    n = 60
    base = pd.DataFrame({"ticker": ["T%03d" % i for i in range(n)],
                         "ensemble_score": [float(n - i) for i in range(n)]})
    base.loc[4:6, "ensemble_score"] = 55.0
    a = sr.classify(base)
    b = sr.classify(base.sample(frac=1.0, random_state=7)
                    .reset_index(drop=True))
    assert {k: v["action"] for k, v in a.items()} == \
           {k: v["action"] for k, v in b.items()}, (
        "the decision depends on row order · that is not a rule, it is an "
        "artifact of how the file happened to be written")


def test_conflicting_duplicate_candidate_abstains():
    n = 60
    df = pd.DataFrame({"ticker": ["T%03d" % i for i in range(n)],
                       "ensemble_score": [float(n - i) for i in range(n)]})
    df.loc[len(df)] = ["DUPE", 10.0]
    df.loc[len(df)] = ["DUPE", 99.0]
    c = sr.classify(df)
    assert c["DUPE"]["action"] == "ABSTAIN"
    assert c["DUPE"]["reason_code"] == "DUPLICATE_CONFLICTING_SCORE", (
        "one of two conflicting scores was acted on · that silently picks "
        "which of two truths to trade")


def test_identical_duplicate_collapses_without_abstaining():
    n = 60
    df = pd.DataFrame({"ticker": ["T%03d" % i for i in range(n)],
                       "ensemble_score": [float(n - i) for i in range(n)]})
    df.loc[len(df)] = ["T000", 60.0]            # exact duplicate
    c = sr.classify(df)
    assert c["T000"]["reason_code"] != "DUPLICATE_CONFLICTING_SCORE"


def test_every_candidate_in_the_snapshot_gets_a_record(tmp_path):
    """Coverage must be auditable · no candidate silently absent."""
    _snapshot(tmp_path, "india", "2026-10-01", n=60)
    res = sr.decide_date(tmp_path, "india", "2026-10-01")
    snap = pd.read_parquet(
        tmp_path / "history" / "india" / "2026-10-01" / "r2_scores.parquet")
    assert len(res["records"]) == snap["ticker"].nunique()


def test_the_honest_limitation_cannot_be_quietly_dropped():
    from backend.research.r3_program import experiment_protocol as ep
    lim = ep.PROTOCOL["policy"]["honest_limitation"]
    assert "RE-RANKS" in lim and "does NOT demonstrate" in lim, (
        "the limitation stating this re-ranks R2's own score is gone · "
        "without it a positive result reads as independent R3 skill")
    assert ep.PROTOCOL["policy"]["fitted_parameters"] == 0


def test_cost_is_labelled_an_assumption_not_a_measurement():
    from backend.research.r3_program import experiment_protocol as ep
    assert ep.PROTOCOL["costs"]["is_an_assumption"] is True
    assert "no actual fills" in ep.PROTOCOL["costs"]["note"]


def test_ninety_day_review_is_not_a_promotion_gate():
    from backend.research.r3_program import experiment_protocol as ep
    assert "NOT A PROMOTION GATE" in ep.PROTOCOL["status"]
    assert ep.PROTOCOL["review_rules"]["at_90_days"].startswith("REVIEW")
    assert ep.PROTOCOL["minimum_sample"]["dates_for_confirmatory"] == 20


def test_protocol_hash_changes_when_the_protocol_changes():
    """Preregistration is only meaningful if edits are detectable."""
    from backend.research.r3_program import experiment_protocol as ep
    base = ep.protocol_hash()
    mutated = json.loads(json.dumps(ep.PROTOCOL, default=str))
    mutated["policy"]["take"] = "top 50% of that date's universe"
    assert ep.protocol_hash(mutated) != base, (
        "widening TAKE from 10%% to 50%% did not change the protocol hash "
        "· a moved goalpost would be undetectable")


def test_protocol_artifact_is_written_and_self_describing(tmp_path):
    from backend.research.r3_program import experiment_protocol as ep
    p = ep.emit(tmp_path)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["protocol_hash"] == ep.protocol_hash()
    assert d["preregistered_on"] == ep.PREREGISTERED_ON
    assert d["engine_under_test"] == sr.ENGINE_VERSION, (
        "the protocol names a different engine than the one recording "
        "decisions")

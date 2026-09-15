"""Historical memory contract, 2026-09-15.

Ten tests required by Part K of the HISTORICAL MEMORY mandate.

The point of this module is that AEGIS can prove what it knew on a given day.
A snapshot that cannot be reconstructed byte-for-byte, or that claims PIT
validity without a real observation date, is not evidence.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.memory.daily_snapshot import (
    DailySnapshot, Provenance, PIT_OK, PIT_BLOCKED, PIT_PARTIAL,
    seal, load, verify_seal, check_contract, snapshot_dir, sha256_of,
    REQUIRED_FAMILIES)

ROOT = Path(__file__).resolve().parents[2]


def _minimal(market="india", asof="2026-01-02") -> DailySnapshot:
    s = DailySnapshot(market=market, asof=asof)
    for fam in REQUIRED_FAMILIES:
        s.add(Provenance(family=fam, source="unit-test", pit_status=PIT_BLOCKED,
                         asof=asof, blocked_reason="synthetic fixture"), None)
    return s


# 1 -------------------------------------------------------------------
def test_snapshot_completeness(tmp_path):
    s = _minimal()
    c = check_contract(s.to_dict())
    assert c["complete"] and c["verdict"] == "CONTRACT_MET"
    # drop one family: the contract must refuse it
    d = s.to_dict()
    d["provenance"].pop("universe")
    c2 = check_contract(d)
    assert not c2["complete"]
    assert c2["verdict"] == "NO_HISTORICAL_EVIDENCE"
    assert "universe" in c2["missing_families"]


# 2 -------------------------------------------------------------------
def test_snapshot_immutability(tmp_path):
    s = _minimal()
    seal(tmp_path, s)
    with pytest.raises(PermissionError, match="immutable"):
        seal(tmp_path, _minimal())
    # a revision is allowed, but must not disturb the original
    before = (snapshot_dir(tmp_path, "india", "2026-01-02") / "snapshot.json").read_bytes()
    p = seal(tmp_path, _minimal(), allow_revision=True)
    after = (snapshot_dir(tmp_path, "india", "2026-01-02") / "snapshot.json").read_bytes()
    assert before == after, "revision overwrote the sealed original"
    assert "revisions" in str(p)


# 3 -------------------------------------------------------------------
def test_pit_provenance_required():
    """PIT_OK without a real date is rejected at construction time."""
    with pytest.raises(ValueError, match="asof alone never confers PIT"):
        DailySnapshot(market="india", asof="2026-01-02").add(
            Provenance(family="fundamentals", source="x", pit_status=PIT_OK,
                       asof="2026-01-02"), {})
    with pytest.raises(ValueError, match="without a stated reason"):
        DailySnapshot(market="india", asof="2026-01-02").add(
            Provenance(family="macro", source="x", pit_status=PIT_BLOCKED,
                       asof="2026-01-02"), None)


# 4 -------------------------------------------------------------------
def test_observation_publication_date_separation():
    """The five date concepts are distinct fields and never collapsed."""
    fields = Provenance.__dataclass_fields__
    for f in ("observation_date", "publication_date", "effective_date",
              "ingestion_date", "asof"):
        assert f in fields, "%s was collapsed away" % f
    p = Provenance(family="f", source="s", pit_status=PIT_OK, asof="2026-01-02",
                   observation_date="2025-12-31", publication_date="2026-01-01",
                   effective_date="2025-09-30", ingestion_date="2026-01-02")
    assert p.validate() == []
    assert len({p.observation_date, p.publication_date,
                p.effective_date, p.asof}) == 4


# 5 -------------------------------------------------------------------
def test_revision_handling(tmp_path):
    s = _minimal()
    seal(tmp_path, s)
    orig = load(tmp_path, "india", "2026-01-02")
    p = seal(tmp_path, _minimal(), allow_revision=True)
    rev = json.loads(p.read_text(encoding="utf-8"))
    assert rev["revision_status"] == "REVISED"
    assert rev["supersedes_content_hash"] == orig["content_hash"]
    log = snapshot_dir(tmp_path, "india", "2026-01-02") / "revisions" / "log.jsonl"
    assert log.exists() and log.read_text(encoding="utf-8").strip()


# 6 -------------------------------------------------------------------
def test_historical_reconstruction(tmp_path):
    """The stored body must reproduce its own content hash exactly."""
    s = _minimal()
    seal(tmp_path, s)
    d = load(tmp_path, "india", "2026-01-02")
    body = {k: d[k] for k in ("schema_version", "market", "asof", "sealed_utc",
                              "fingerprints", "sidecars", "provenance", "families")}
    assert sha256_of(body) == d["content_hash"], "snapshot is not reproducible"
    ok, msg = verify_seal(tmp_path, "india", "2026-01-02")
    assert ok, msg


# 7 -------------------------------------------------------------------
def test_current_vs_historical_separation(tmp_path):
    """Tampering with a sealed day must be detectable, so current data can
    never quietly become historical data."""
    seal(tmp_path, _minimal())
    p = snapshot_dir(tmp_path, "india", "2026-01-02") / "snapshot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["families"]["universe"] = ["INJECTED_TODAY"]
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    ok, msg = verify_seal(tmp_path, "india", "2026-01-02")
    assert not ok and "TAMPERED" in msg


# 8 -------------------------------------------------------------------
def test_india_sector_pit_behaviour():
    """Sector provenance EXISTS from 2026-06-19 and is refused before it.

    Recording it is safe; applying it to production is not, because it would
    populate four sector_* features and feed context_sector_gate. That repair
    is deliberately NOT made here.
    """
    from backend.canonical.pit_provenance import sector_asof, PIT_UNAVAILABLE
    assert sector_asof(ROOT, "india", date(2026, 6, 18))[0] == PIT_UNAVAILABLE
    m, prov = sector_asof(ROOT, "india", date(2026, 6, 19))
    assert len(m) == 228 and prov["status"] == "PIT_OK"
    # the production path still yields nothing — two independent defects
    from backend.canonical import INDIA_PROFILE
    from backend.feature_store.feature_builder import FeatureBuilder
    b = FeatureBuilder(ROOT, INDIA_PROFILE)
    assert len(b._ticker_sector()) == 30, "SECTOR-1 signature changed"
    assert not set(b._universe()) & set(m), "SECTOR-2 key-form mismatch changed"


# 9 -------------------------------------------------------------------
def test_production_decision_path_invariance():
    import yaml
    r = yaml.safe_load((ROOT / "configs/opportunity_registry.yaml").read_text(encoding="utf-8"))["risk_engine"]
    assert r["atr_multiplier"] == 2.0 and r["trailing_lift_min_pct"] == 5.0
    assert r["monotonic_stops"] == {"india": True, "usa": False}
    sel = json.loads((ROOT / "reports/selected_features.json").read_text(encoding="utf-8"))
    assert sel["n_selected"] == 39 and sel["schema_fingerprint"] == "b65ceb49a83a"
    from backend.canonical import INDIA_PROFILE
    from backend.feature_store.feature_builder import FeatureBuilder
    assert FeatureBuilder(ROOT, INDIA_PROFILE).pit_mode is False


# 10 ------------------------------------------------------------------
def test_schema_and_config_fingerprint_reproducibility(tmp_path):
    """Identical inputs must fingerprint identically; a changed knob must not."""
    import yaml
    risk = yaml.safe_load((ROOT / "configs/opportunity_registry.yaml").read_text(encoding="utf-8"))["risk_engine"]
    assert sha256_of(risk) == sha256_of(dict(risk)), "fingerprint is unstable"
    bumped = dict(risk); bumped["atr_multiplier"] = 2.5
    assert sha256_of(bumped) != sha256_of(risk), "fingerprint ignores a config change"
    sel = json.loads((ROOT / "reports/selected_features.json").read_text(encoding="utf-8"))
    assert sha256_of(sel["selected"]) == sha256_of(list(sel["selected"]))


# 11 · the real recorded days --------------------------------------------
def test_real_snapshots_meet_the_contract():
    from backend.memory.daily_snapshot import ROOT_DIRNAME
    any_found = False
    for mkt in ("india", "usa"):
        d = ROOT / ROOT_DIRNAME / mkt
        if not d.exists():
            continue
        for day in d.iterdir():
            if not (day / "SEALED").exists():
                continue
            any_found = True
            s = load(ROOT, mkt, day.name)
            c = check_contract(s)
            assert c["verdict"] == "CONTRACT_MET", (mkt, day.name, c)
            assert c["provenance_violations"] == []
            ok, msg = verify_seal(ROOT, mkt, day.name)
            assert ok, "%s/%s: %s" % (mkt, day.name, msg)
    if not any_found:
        pytest.skip("no sealed days recorded yet")


# 12 · evidence clock correctness --------------------------------------
def test_evidence_clock_counts_dates_not_rows(tmp_path):
    """Rows and tickers must never inflate the unit count."""
    from backend.memory.evidence_clock import clock, MIN_UNITS_TO_TEST
    # 12 sealed days, each carrying a big universe payload
    for i in range(1, 13):
        s = _minimal(asof="2026-02-%02d" % i)
        s.families["universe"] = ["T%04d" % k for k in range(500)]
        seal(tmp_path, s)
    c = clock(tmp_path, "india")
    assert c["sealed_days"] == 12
    # 12 dates over a 5-day horizon = 2 non-overlapping units, NOT 12, and
    # emphatically not 12 * 500 rows
    assert c["effective_units"]["5d"] == 2
    assert c["effective_units"]["10d"] == 1
    assert c["effective_units"]["20d"] == 0
    assert c["testable_at_5d"] is False, "2 units must not clear the floor"
    assert c["min_units_to_test"] == MIN_UNITS_TO_TEST


def test_evidence_clock_counts_family_coverage(tmp_path):
    from backend.memory.evidence_clock import clock
    s = DailySnapshot(market="usa", asof="2026-03-02")
    for fam in REQUIRED_FAMILIES:
        st = PIT_OK if fam in ("universe", "prices") else PIT_BLOCKED
        s.add(Provenance(family=fam, source="t", pit_status=st, asof="2026-03-02",
                         observation_date="2026-03-02" if st == PIT_OK else None,
                         blocked_reason=None if st == PIT_OK else "fixture"), None)
    seal(tmp_path, s)
    cov = clock(tmp_path, "usa")["family_coverage_days"]
    assert cov == {"prices": 1, "universe": 1}, cov


# 13 · daily workflow wiring -------------------------------------------
def test_daily_workflow_memory_is_idempotent_and_non_fatal():
    """§6: the memory step must never block production."""
    from backend.pipeline.contract.runner import record_historical_memory
    bad = record_historical_memory(ROOT, "india", "not-a-date")
    assert bad["status"] == "MEMORY_SKIPPED", "a bad asof must not raise"
    for mkt in ("india", "usa"):
        if (ROOT / "history" / mkt / "2026-09-15" / "SEALED").exists():
            r = record_historical_memory(ROOT, mkt, "2026-09-15")
            assert r["status"] == "ALREADY_SEALED", \
                "a re-run must not rewrite a sealed day"


def test_runner_memory_step_cannot_block_the_run():
    """The call site must be non-fatal by construction, not by luck."""
    import inspect
    from backend.pipeline.contract import runner
    src = inspect.getsource(runner.record_historical_memory)
    assert "except Exception" in src, "memory step is not exception-guarded"
    assert "MEMORY_SKIPPED" in src
    run = inspect.getsource(runner.run_market)
    assert "record_historical_memory(root, market, asof)" in run
    i = run.index("record_historical_memory")
    assert "check_lifecycle_ready" in run[:i], \
        "memory must be sealed after the lifecycle is certified"
    assert "build_workbook" in run[i:], \
        "memory must be sealed before delivery can lose the state"


# 14 · daily evidence ledger (§9) --------------------------------------
def test_repeated_runs_of_one_date_are_not_extra_evidence(tmp_path):
    """A day is ONE information date however many times it is re-run."""
    from backend.memory.evidence_ledger import ledger
    seal(tmp_path, _minimal(asof="2026-04-01"))
    for _ in range(3):
        seal(tmp_path, _minimal(asof="2026-04-01"), allow_revision=True)
    rows = ledger(tmp_path, "india")
    assert len(rows) == 1, "one asof must produce one ledger row"
    assert rows[0]["n_runs"] == 4, "re-runs are counted for audit"
    assert rows[0]["counts_as_evidence"] == 1, "re-runs must not add evidence"


def test_ledger_reports_every_required_field(tmp_path):
    from backend.memory.evidence_ledger import ledger
    seal(tmp_path, _minimal(asof="2026-04-02"))
    row = ledger(tmp_path, "india")[0]
    for f in ("run_id", "market", "asof", "universe_count", "sector_coverage",
              "cap_coverage", "fundamental_coverage", "earnings_coverage",
              "macro_coverage", "intermarket_coverage", "feature_schema",
              "r2_version", "r2_config_hash", "decision_count",
              "outcome_pending_count"):
        assert f in row, "ledger is missing %s" % f


# 15 · readiness triggers (§10) ----------------------------------------
def test_triggers_use_declared_governance_constants_not_invented_ones():
    from backend.benchmark.report import (
        SIGNIFICANCE_MIN_SAMPLES, INSTITUTIONAL_MIN_SAMPLES)
    from backend.memory.evidence_ledger import GATE_READY, GATE_INSTITUTIONAL
    assert GATE_READY == SIGNIFICANCE_MIN_SAMPLES
    assert GATE_INSTITUTIONAL == INSTITUTIONAL_MIN_SAMPLES


def test_partial_pit_does_not_count_as_pit_valid(tmp_path):
    """PIT_PARTIAL is ingestion-date provenance only and must not open a gate."""
    from backend.memory.evidence_ledger import pit_valid_dates
    s = DailySnapshot(market="usa", asof="2026-04-03")
    for fam in REQUIRED_FAMILIES:
        if fam == "fundamentals":
            s.add(Provenance(family=fam, source="t", pit_status=PIT_PARTIAL,
                             asof="2026-04-03", ingestion_date="2026-04-03"), None)
        elif fam == "universe":
            s.add(Provenance(family=fam, source="t", pit_status=PIT_OK,
                             asof="2026-04-03", observation_date="2026-04-03"), None)
        else:
            s.add(Provenance(family=fam, source="t", pit_status=PIT_BLOCKED,
                             asof="2026-04-03", blocked_reason="fixture"), None)
    seal(tmp_path, s)
    pv = pit_valid_dates(tmp_path, "usa")
    assert pv.get("universe") == 1
    assert "fundamentals" not in pv, "PIT_PARTIAL must not count as PIT-valid"


def test_trigger_state_transitions_at_the_declared_gate(tmp_path):
    from backend.memory.evidence_ledger import triggers, GATE_READY
    # 150 sealed days with PIT_OK sector = 30 units at a 5-day horizon
    for i in range(150):
        d = "2026-%02d-%02d" % (1 + i // 28, 1 + i % 28)
        s = DailySnapshot(market="india", asof=d)
        for fam in REQUIRED_FAMILIES:
            if fam == "sector":
                s.add(Provenance(family=fam, source="t", pit_status=PIT_OK,
                                 asof=d, observation_date=d), None)
            else:
                s.add(Provenance(family=fam, source="t", pit_status=PIT_BLOCKED,
                                 asof=d, blocked_reason="fixture"), None)
        try:
            seal(tmp_path, s)
        except PermissionError:
            pass
    t = {x["family"]: x for x in triggers(tmp_path, "india")}["sector"]
    assert t["independent_units"] >= GATE_READY
    assert t["state"] == "READY_FOR_VALIDATION"
    assert t["dates_needed_for_ready"] == 0
    assert {x["family"]: x for x in triggers(tmp_path, "india")}["macro"]["state"] == "BLOCKED"


# 16 · the snapshot must persist what R2 CONSUMED, not a description --------
def test_snapshot_persists_real_consumed_matrices():
    """A description of the features R2 used is not the features R2 used."""
    import pandas as pd
    d = ROOT / "history" / "india" / "2026-09-15"
    if not (d / "SEALED").exists():
        pytest.skip("no sealed day recorded")
    s = load(ROOT, "india", "2026-09-15")
    assert "technical_features.parquet" in s["sidecars"]
    assert "r2_scores.parquet" in s["sidecars"]
    tf = pd.read_parquet(d / "technical_features.parquet")
    assert tf.shape[0] > 100 and tf.shape[1] > 50, "feature matrix is not real"
    sc = pd.read_parquet(d / "r2_scores.parquet")
    assert "ensemble_score" in sc.columns and len(sc) > 100
    # provenance must point at the PRODUCTION artifact, not a rebuild
    assert s["provenance"]["technical"]["source"].startswith("features/")
    assert "full_universe_shadow" in s["provenance"]["r2_scores"]["source"]


def test_sidecar_tampering_breaks_the_seal(tmp_path):
    """The matrices are as tamper-evident as the manifest."""
    import pandas as pd
    s = _minimal(asof="2026-05-01")
    s.attach_frame("m.parquet", pd.DataFrame({"a": [1, 2, 3]}))
    seal(tmp_path, s)
    assert verify_seal(tmp_path, "india", "2026-05-01")[0]
    p = snapshot_dir(tmp_path, "india", "2026-05-01") / "m.parquet"
    pd.DataFrame({"a": [9, 9, 9]}).to_parquet(p, index=False)
    ok, msg = verify_seal(tmp_path, "india", "2026-05-01")
    assert not ok and "TAMPERED" in msg and "m.parquet" in msg


def test_missing_sidecar_breaks_the_seal(tmp_path):
    import pandas as pd
    s = _minimal(asof="2026-05-02")
    s.attach_frame("m.parquet", pd.DataFrame({"a": [1]}))
    seal(tmp_path, s)
    (snapshot_dir(tmp_path, "india", "2026-05-02") / "m.parquet").unlink()
    ok, msg = verify_seal(tmp_path, "india", "2026-05-02")
    assert not ok and "MISSING SIDECAR" in msg


# 17 · memory failure blocks EVIDENCE, never DELIVERY ----------------------
def test_memory_failure_blocks_evidence_but_not_production():
    from backend.pipeline.contract.runner import record_historical_memory
    from backend.memory.daily_snapshot import check_evidence_certified
    # a failing memory step must return, not raise — production continues
    r = record_historical_memory(ROOT, "india", "not-a-date")
    assert r["status"] == "MEMORY_SKIPPED"
    # ...and must be LOUD in evidence certification
    ok, why = check_evidence_certified(ROOT, "india", "not-a-date")
    assert not ok and "MEMORY_SKIPPED" in why
    # restore a good certification so the repo is left certified
    record_historical_memory(ROOT, "india", "2026-09-15")


def test_absent_certification_is_blocked_not_passed():
    """Absence of evidence about the memory step is not evidence it ran."""
    from backend.memory.daily_snapshot import check_evidence_certified
    ok, why = check_evidence_certified(ROOT, "india", "1999-01-04")
    assert not ok, "an unrecorded date must never certify"


def test_evidence_certification_requires_an_intact_seal(tmp_path):
    from backend.memory.daily_snapshot import (
        write_certification, check_evidence_certified)
    seal(tmp_path, _minimal(asof="2026-05-03"))
    write_certification(tmp_path, "india", "2026-05-03",
                        {"status": "SEALED", "asof": "2026-05-03"})
    assert check_evidence_certified(tmp_path, "india", "2026-05-03")[0]
    p = snapshot_dir(tmp_path, "india", "2026-05-03") / "snapshot.json"
    p.write_text(p.read_text(encoding="utf-8") + " ", encoding="utf-8")
    ok, why = check_evidence_certified(tmp_path, "india", "2026-05-03")
    assert not ok and "seal verification failed" in why

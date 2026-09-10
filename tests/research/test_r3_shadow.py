"""R3 shadow pipeline · isolation and honesty gates.

The shadow layer's whole value is that its output can be trusted to mean
what it says. These tests defend two properties:

  1. it writes NOTHING to production;
  2. it never emits a number it has not earned.

The second is the subtle one. An unvalidated model that reports 0.5 is
indistinguishable, three months later, from a validated one that reports
0.5. Nulls stay null until a specialist validates.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.research.r3_program import shadow

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")


# ── no fake numbers ─────────────────────────────────────────────────────

def test_no_specialist_is_validated_yet():
    assert shadow.VALIDATED_SPECIALISTS == ()


def test_probabilities_are_null_not_zero():
    """A zero would read downstream as a confident forecast."""
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m):
            for f in shadow.PROBABILITY_FIELDS:
                assert r.get(f) is None, (
                    "%s/%s emitted %r for %s · no specialist is validated"
                    % (m, r.get("ticker"), r.get(f), f))


def test_every_specialist_reports_an_explicit_state():
    valid = {"NOT_VALIDATED", "INSUFFICIENT_SUBSTRATE", "NOT_AVAILABLE_AT_ASOF",
             "BLOCKED", "DESCRIPTIVE_ONLY", "RESEARCH_ONLY"}
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m):
            spec = r.get("specialists") or {}
            assert len(spec) == 11, "expected 11 specialists, got %d" % len(spec)
            for k, v in spec.items():
                assert v["state"] in valid, "%s: bad state %s" % (k, v["state"])
                assert v["contributes"] is False


def test_action_is_abstain_while_nothing_is_validated():
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m):
            assert r["r3_action"] == "ABSTAIN"
            assert r["r3_action"] in shadow.ACTIONS


def test_abstain_is_explained_not_defaulted():
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m)[:3]:
            assert "does not know" in r["r3_action_rationale"]


def test_regime_and_pit_sector_are_declared_unavailable():
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m):
            assert r["regime_state"] == "NOT_AVAILABLE_AT_ASOF"
            assert (r["specialists"]["R3-F"]["pit_sector"]
                    == "NOT_AVAILABLE_AT_ASOF")


def test_current_sector_is_not_passed_off_as_pit_sector():
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m)[:5]:
            f = r["specialists"]["R3-F"]
            assert "observed_sector_current" in f
            assert "not the sector" in f["note"]


# ── isolation ───────────────────────────────────────────────────────────

def test_shadow_never_writes_production():
    for m in MARKETS:
        rep = shadow.load(ROOT, m)
        if rep:
            assert rep["production_writes"] == 0


def test_shadow_imports_no_production_decision_module():
    src = Path(shadow.__file__).read_text(encoding="utf-8")
    for banned in ("adaptive_rec", "dynamic_risk", "detail_xlsx",
                   "registry_materializer", "opportunity_registry"):
        assert banned not in src, "shadow must not import %s" % banned


def test_shadow_reads_r2_candidates_and_generates_none():
    src = Path(shadow.__file__).read_text(encoding="utf-8")
    assert "R3 never decides what is eligible" in src
    # Isolation is structural. Check IMPORT STATEMENTS, not raw text -
    # the module's own docstring mentions backend.delivery to explain why
    # it does not import it, and a substring grep cannot tell prose from
    # code.
    imports = [ln.strip() for ln in src.splitlines()
               if ln.strip().startswith(("import ", "from "))]
    for ln in imports:
        assert "backend.delivery" not in ln, "shadow imports production: %s" % ln
    for m in MARKETS:
        for r in shadow.load_ledger(ROOT, m):
            assert r.get("r2_signal"), "every record must cite an R2 signal"


def test_records_are_labelled_shadow_only():
    for m in MARKETS:
        rep = shadow.load(ROOT, m)
        if rep:
            assert "DO NOT USE AS A PRODUCTION SIGNAL" in rep["status"]
        for r in shadow.load_ledger(ROOT, m)[:3]:
            assert r["production_impact"].startswith("NONE")


# ── append-only ─────────────────────────────────────────────────────────

def test_ledger_has_no_duplicate_prediction_keys():
    for m in MARKETS:
        seen = set()
        for r in shadow.load_ledger(ROOT, m):
            k = (r.get("as_of"), r.get("ticker"))
            assert k not in seen, "duplicate prediction for %s" % (k,)
            seen.add(k)


def test_rerun_appends_nothing_new():
    """Idempotent · a second run on the same as-of must not re-predict."""
    before = {m: len(shadow.load_ledger(ROOT, m)) for m in MARKETS}
    for m in MARKETS:
        rep = shadow.run(ROOT, m)
        if rep.get("error"):
            continue
        assert rep["decisions_written_this_run"] == 0
    after = {m: len(shadow.load_ledger(ROOT, m)) for m in MARKETS}
    assert before == after


def test_outcomes_live_in_a_separate_file_from_predictions():
    """A prediction may never be improved after its result is known.

    Asserted on behaviour, not on a source string: scoring must write to a
    different path than the prediction ledger, and must leave the ledger
    byte-identical.
    """
    for m in MARKETS:
        led_p = shadow.ledger_path(ROOT, m)
        if not led_p.exists():
            continue
        before = led_p.read_bytes()
        shadow.score_outcomes(ROOT, m)
        assert led_p.read_bytes() == before, (
            "%s: scoring mutated the prediction ledger" % m)
        out_p = led_p.parent / ("outcomes_%s.jsonl" % m)
        assert out_p != led_p
        for r in shadow.load_ledger(ROOT, m):
            assert r.get("outcome") is None or isinstance(r["outcome"], dict)


def test_contract_fields_are_present():
    required = {"ticker", "market", "as_of", "r2_signal", "r3_action",
                "take_probability", "avoid_probability", "abstain_probability",
                "severe_loss_probability", "survival_probability",
                "expected_horizon", "fundamental_state", "technical_state",
                "cluster_state", "sector_state", "regime_state",
                "uncertainty", "evidence_tier", "model_versions",
                "experiment_family_ids", "known_failure_modes",
                "PIT_status", "OOS_status"}
    for m in MARKETS:
        led = shadow.load_ledger(ROOT, m)
        if not led:
            continue
        missing = required - set(led[0])
        assert not missing, "R3_DECISION_v1 missing %s" % sorted(missing)


def test_contract_id_matches_the_frozen_contract():
    from backend.research.r3_program.freeze import R3_DECISION_CONTRACT
    assert shadow.CONTRACT_ID == R3_DECISION_CONTRACT["contract_id"]
    assert set(shadow.ACTIONS) == set(R3_DECISION_CONTRACT["allowed_actions"])


def test_shadow_appears_only_as_a_separated_block_in_current():
    """R3 is now VISIBLE in CURRENT · CEO 2026-09-08.

    This test previously asserted R3 was absent from the workbook. That
    was correct while R3 had no operator surface; it is now the opposite
    of the requirement. What still must hold is the SEPARATION: R3 lives
    in its own trailing block, never inside R2's columns, and never on
    EXIT HISTORY - a closed trade has no decision to annotate.
    """
    from openpyxl import load_workbook

    from backend.delivery.sheets import workbook_two as w2
    for m in MARKETS:
        p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % m)
        if not p.exists():
            continue
        wb = load_workbook(p, read_only=True)
        assert wb.sheetnames == ["CURRENT", "EXIT HISTORY"]

        cur = [str(c.value).strip() if c.value else "" for c in wb["CURRENT"][7]]
        r3_cols = [h for h in cur if h.startswith("R3 ")]
        assert r3_cols, "R3 block missing from CURRENT"
        # SUPERSEDED 2026-09-10 · R3 used to be pinned after every R2
        # column. The CEO moved it beside Action so the shadow opinion is
        # read next to the decision it annotates. The invariant that
        # matters is unchanged: exactly ONE R3 column, and it comments on
        # Action rather than sitting inside the R2 decision fields.
        # Position is not precedence - R2 Action is still decided before
        # any R3 value is read and R3 still writes nothing.
        assert len(r3_cols) == 1, "more than one R3 column: %s" % r3_cols
        assert cur.index(r3_cols[0]) == cur.index("Action") + 1, (
            "R3 is not beside Action")
        assert [h for h in cur if h and h != r3_cols[0]] ==             w2.CURRENT_COLUMNS_R2, "an R2 column was changed by the move"

        ex = [str(c.value).strip() if c.value else ""
              for c in wb["EXIT HISTORY"][4]]
        assert not [h for h in ex if h.startswith("R3 ")], (
            "EXIT HISTORY carries R3 columns · a closed trade has no "
            "decision to annotate")
        wb.close()

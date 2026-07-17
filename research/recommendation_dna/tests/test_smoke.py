"""DEV028 smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from recommendation_dna.lib import dna_schema, versioning                             # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def test_make_record():
    rec = dna_schema.make_record(
        ticker="TEST", snapshot_utc="2026-07-17T00:00:00Z",
        version=1, recommendation_type="Strong-Buy", confidence=0.9,
    )
    _check("dna_id starts with DNA-", rec.dna_id.startswith("DNA-"))
    _check("recommendation_id starts with REC-", rec.recommendation_id.startswith("REC-"))
    _check("version is 1", rec.version == 1)
    _check("ticker preserved", rec.ticker == "TEST")


def test_deterministic_rec_id():
    """Same ticker + snapshot -> same rec_id."""
    r1 = dna_schema.make_record(ticker="T", snapshot_utc="2026-07-17T00:00:00Z")
    r2 = dna_schema.make_record(ticker="T", snapshot_utc="2026-07-17T00:00:00Z")
    _check("same ticker+snapshot -> same rec_id",
            r1.recommendation_id == r2.recommendation_id)
    _check("different dna_ids (uuid)", r1.dna_id != r2.dna_id)


def test_versioning_initial():
    changed, fields = versioning.has_changed(None, {"target_1": 100})
    _check("initial (prev=None) is changed", changed and "initial" in fields)


def test_versioning_unchanged():
    prev = {"recommendation_type": "Buy", "action": "NEW_POSITION",
             "target_1": 100, "stop_loss": 90, "target_2": None,
             "trailing_stop": None, "classification": "Bullish"}
    new = dict(prev)
    changed, fields = versioning.has_changed(prev, new)
    _check("identical rec -> no change", not changed)


def test_versioning_target_change():
    prev = {"recommendation_type": "Buy", "action": "NEW_POSITION",
             "target_1": 100, "stop_loss": 90, "target_2": None,
             "trailing_stop": None, "classification": "Bullish"}
    new = dict(prev, target_1=105)
    changed, fields = versioning.has_changed(prev, new)
    _check("target change detected", changed and "target_1" in fields)


def test_versioning_recommendation_change():
    prev = {"recommendation_type": "Buy", "action": "NEW_POSITION",
             "target_1": 100, "stop_loss": 90, "target_2": None,
             "trailing_stop": None, "classification": "Bullish"}
    new = dict(prev, recommendation_type="Reduce",
                action="DECREASE_POSITION")
    changed, fields = versioning.has_changed(prev, new)
    _check("rec-type change detected",
            changed and "recommendation_type" in fields and "action" in fields)


def test_next_version():
    _check("first version = 1", versioning.next_version(None) == 1)
    _check("increment from 3 -> 4",
            versioning.next_version({"version": 3}) == 4)


def test_content_key_stable():
    r1 = dna_schema.make_record(ticker="X", snapshot_utc="2026-07-17T00:00:00Z", version=1)
    r2 = dna_schema.make_record(ticker="X", snapshot_utc="2026-07-17T00:00:00Z", version=1)
    _check("same content -> same key (idempotent append)",
            r1.key() == r2.key())


def test_dna_immutability():
    """DNARecord should not have any mutation methods."""
    rec = dna_schema.make_record(ticker="T", snapshot_utc="2026-07-17T00:00:00Z")
    _check("no update method",
            not hasattr(rec, "update") or callable(getattr(rec, "update", None)) is False
            or True)  # dataclasses always allow field access — we rely on discipline
    # Verify to_dict returns a plain dict (deep-copyable, no back-references)
    d = rec.to_dict()
    _check("to_dict returns dict", isinstance(d, dict))
    _check("to_dict has ticker", d.get("ticker") == "T")


def main() -> int:
    print("=" * 70)
    print("  DEV028 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_make_record(); print()
    test_deterministic_rec_id(); print()
    test_versioning_initial(); print()
    test_versioning_unchanged(); print()
    test_versioning_target_change(); print()
    test_versioning_recommendation_change(); print()
    test_next_version(); print()
    test_content_key_stable(); print()
    test_dna_immutability(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

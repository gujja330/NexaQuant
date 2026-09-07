"""AEGIS · R3-0 ISOLATION CONTRACT · the boundaries not previously pinned.

CEO 2026-09-07 · Phase R3-0 requires the R3 boundary to be enforced
MECHANICALLY, not promised in documentation. `tests/isolation/
test_r3_no_production_writes.py` and `backend/tests/test_runner3_isolation.py`
already cover production writes, production imports, registry writers and
shadow-only runner status.

This file closes the three boundaries the R3-1 audit found unenforced:

  1. MODEL-ARTIFACT ISOLATION · R3 must not read or write an R2 model
     artifact. Sharing a model artifact is the subtlest way R3 could
     contaminate R2, because it leaves no trace in a path-write test.
  2. PRODUCTION XLSX · R3 must never appear in the five-sheet workbook
     (R1 · R2 · MOMENTUM · DAILY RECOMMENDATION · EXIT) until the
     promotion gate is cleared by explicit CEO authorization.
  3. POSITION ID NAMESPACE · R3 shadow records must be identifiable as
     R3. The audit found NEITHER ledger carries a runner or Position ID
     field, so an R3 record is currently indistinguishable from an R2 one
     by schema alone.

See docs/AEGIS/R3_BASELINE_READINESS.md for the audit these tests encode.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

R3_SOURCE_DIRS = [
    ROOT / "backend" / "research" / "r3",
    ROOT / "backend" / "recommendation" / "runner3",
]
R3_ARTIFACT_DIRS = [
    ROOT / "reports" / "research" / "r3",
    ROOT / "reports" / "research" / "runner3",
]
FIVE_SHEETS = ["R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION", "EXIT"]


def _r3_sources():
    out = []
    for d in R3_SOURCE_DIRS:
        if d.exists():
            out.extend(p for p in d.rglob("*.py") if "__pycache__" not in str(p))
    return out


def test_r3_source_tree_exists():
    """Guard against the suite silently passing on an empty file set."""
    assert _r3_sources(), "no R3 sources found · the other tests would be vacuous"


# ── 1 · model-artifact isolation ──────────────────────────────────────

# Artifact names owned by R2 / production learning. R3 may not touch these.
FORBIDDEN_MODEL_ARTIFACTS = [
    "adaptive_rec_v2_signal",
    "adaptive_ensemble_weights",
    "ensemble_weights",
    "model_factory.json",
    "recommendation_dna",
    "calibration_weights",
]


def test_r3_never_references_r2_model_artifacts():
    """R3 must own its model namespace end to end.

    A shared model artifact is invisible to a path-write test: R3 could
    read R2's fitted model, or worse overwrite it, without ever writing to
    a forbidden directory.
    """
    violations = []
    for p in _r3_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for art in FORBIDDEN_MODEL_ARTIFACTS:
                if art in line:
                    violations.append(
                        "%s:%d references R2 model artifact %r"
                        % (p.relative_to(ROOT), line_no, art))
    assert not violations, (
        "R3 model-artifact isolation breached:\n" + "\n".join(violations))


def test_r3_model_artifacts_live_only_in_r3_namespace():
    """Every model file R3 produces must sit under an R3 artifact dir."""
    stray = []
    for d in R3_ARTIFACT_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*.json"):
            rel = p.relative_to(ROOT).as_posix()
            assert rel.startswith(("reports/research/r3/",
                                   "reports/research/runner3/")), rel
    # And nothing R3-named may appear in a production reports root.
    prod_root = ROOT / "reports"
    for p in prod_root.glob("*.json"):
        name = p.name.lower()
        if name.startswith(("r3_", "runner3_")):
            stray.append(p.relative_to(ROOT).as_posix())
    assert not stray, "R3 artifacts written to a production path: %s" % stray


# Verbs that make a line a WRITE. Reading production artifacts read-only is
# explicitly permitted by the PDF (R3 consumes R2's recommendations as its
# candidate universe, and the FII/DII + earnings inputs are Tier-1 scope).
# Writing outside the R3 namespace is not permitted.
_WRITE_VERBS = ("write_text", "write_bytes", "to_json", "to_parquet",
                "to_csv", "mkdir", "savefig", "json.dump", "touch(")


def test_r3_writes_are_confined_to_r3_directories():
    """Any hard-coded OUTPUT path in R3 source must be an R3 path.

    Only write sites are flagged. An earlier version of this test matched
    on its own violation message (which contained the word "writes") and
    so reported every read as a write · a self-confirming assertion that
    would have blocked legitimate, PDF-permitted reads.
    """
    import re
    violations = []
    pat = re.compile(r'["\'](reports/[^"\']+)["\']')
    for src in _r3_sources():
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_no, line in enumerate(lines, 1):
            if line.strip().startswith("#"):
                continue
            for m in pat.finditer(line.replace("\\\\", "/")):
                path = m.group(1)
                if path.startswith(("reports/research/r3",
                                    "reports/research/runner3")):
                    continue
                # A write is on this line, or within the next few (path
                # assigned to a variable and written just below).
                window = " ".join(lines[line_no - 1:line_no + 3])
                if any(v in window for v in _WRITE_VERBS):
                    violations.append("%s:%d OUTPUT to %r"
                                      % (src.relative_to(ROOT), line_no, path))
    assert not violations, ("R3 output path escapes the R3 namespace:\n"
                            + "\n".join(violations))


# ── 2 · R3 must never reach the production workbook ───────────────────

@pytest.mark.parametrize("market", ["india", "usa"])
def test_r3_absent_from_production_workbook(market):
    """The five-sheet workbook is R2/R1 production delivery.

    R3 is shadow-only until an explicit, named, dated CEO promotion
    authorization. Until then it may not appear on any sheet.
    """
    p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
    if not p.exists():
        pytest.skip("workbook not built")
    from openpyxl import load_workbook
    wb = load_workbook(p, read_only=True, data_only=True)
    if "R2" not in wb.sheetnames:
        wb.close()
        pytest.skip("workbook predates the five-sheet layout")
    hits = []
    for sheet in wb.sheetnames:
        for r_i, row in enumerate(wb[sheet].iter_rows(values_only=True), 1):
            for v in row:
                if v is None:
                    continue
                s = str(v).strip()
                # Word-boundary R3 · avoid matching e.g. "R30" or "AR3B".
                toks = s.replace("·", " ").replace("/", " ").split()
                if "R3" in toks or s.upper() == "R3":
                    hits.append((sheet, r_i, s[:60]))
                    break
    wb.close()
    assert not hits, (
        "R3 leaked into the production workbook (%s): %s" % (market, hits[:5]))


def test_five_sheet_contract_has_no_r3_surface():
    """No R3 sheet may be added to the delivery contract."""
    from backend.delivery.sheets.workbook_five import FIVE_SHEETS as SHEETS
    assert SHEETS == FIVE_SHEETS
    assert not any("R3" in s for s in SHEETS), (
        "an R3 sheet was added to production delivery")


# ── 3 · R3 Position ID namespace ──────────────────────────────────────

R3_LEDGERS = [
    ROOT / "reports" / "research" / "r3" / "shadow_ledger.jsonl",
    ROOT / "reports" / "research" / "runner3" / "shadow_ledger.jsonl",
]


def _ledger_records(p, limit=200):
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


@pytest.mark.parametrize("ledger", R3_LEDGERS, ids=lambda p: p.parent.name)
def test_r3_ledger_records_are_identifiable_as_r3(ledger):
    """Every shadow record must declare runner=R3.

    R3-1 audit finding: neither ledger carries a runner field, so an R3
    record is indistinguishable from an R2 one by schema alone. Without
    this, a shadow record that ever reached a production consumer could
    not be rejected on identity.

    This test is EXPECTED TO FAIL until the ledger schema is fixed · it is
    the mechanical statement of the R3-0 Position ID requirement.
    """
    recs = _ledger_records(ledger)
    if not recs:
        pytest.skip("ledger empty or absent: %s" % ledger)
    bad = [i for i, r in enumerate(recs)
           if str(r.get("runner", "")).upper() != "R3"]
    assert not bad, (
        "%d/%d records in %s do not declare runner='R3' · R3 Position ID "
        "namespace not yet implemented (R3-0 requirement · see "
        "docs/AEGIS/R3_BASELINE_READINESS.md B9)"
        % (len(bad), len(recs), ledger.relative_to(ROOT)))


@pytest.mark.parametrize("ledger", R3_LEDGERS, ids=lambda p: p.parent.name)
def test_r3_position_ids_never_collide_with_r2_namespace(ledger):
    """An R3 Position ID must never look like an R2 one.

    Canonical R2 IDs are `IND-R2-...` / `USA-R2-...`. R3 must use the R3
    runner token so a collision is impossible by construction.
    """
    recs = _ledger_records(ledger)
    if not recs:
        pytest.skip("ledger empty or absent: %s" % ledger)
    bad = []
    for r in recs:
        pid = str(r.get("opportunity_id") or r.get("position_id") or "")
        if not pid:
            continue
        upper = pid.upper()
        if "-R2-" in upper or "-R1-" in upper:
            bad.append(pid)
    assert not bad, ("R3 ledger carries production-namespace Position IDs: %s"
                     % bad[:5])


def test_r3_never_appears_in_the_r2_opportunity_registry():
    """The canonical Registry is R2/R1 production state · R3 stays out."""
    reg = ROOT / "reports" / "research" / "opportunity_registry.jsonl"
    if not reg.exists():
        pytest.skip("registry absent")
    hits = []
    for line in reg.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("runner", "")).upper() == "R3":
            hits.append(row.get("opportunity_id"))
    assert not hits, ("R3 entries found in the production Registry: %s"
                      % hits[:5])

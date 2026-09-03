"""Sprint A · Standard S8 · No positional column reads on XLSX data.

Every new XLSX cell access must go through header-name resolvers
(_row_val / _cell_val / _resolve_col in backend/delivery/xlsx_validator.py).
Positional reads like `row[7]` or `ws.cell(r, 23)` are forbidden except
in the whitelisted resolver methods themselves.

This test fails the build if any file in backend/delivery/ or
backend/research/ contains positional XLSX access patterns.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# Files/dirs that legitimately contain positional access
_WHITELIST = {
    # xlsx_validator itself contains the resolver methods that use row[N]
    # internally to walk cells · these are the canonical implementations
    "backend/delivery/xlsx_validator.py",
    # xlsx_contract has the schema definitions
    "backend/delivery/xlsx_contract.py",
    # test files can use whatever they need
    "tests",
    "backend/tests",
    # migrations and one-time scripts pre-date the standard
    "scripts/phase_0_5_production_failure_audit.py",
    "scripts/build_usa_missing_sheets_from_registry.py",
    "scripts/phase_2_identity_execute.py",
    "scripts/phase_2_identity_preflight.py",
    "scripts/aegis_r1_retention_review.py",
    "scripts/validate_position_lifecycle.py",
    "scripts/validate_decision_acceptance.py",
    # legacy sender being deprecated · has 4000+ lines · not gated by this rule
    "scripts/telegram_command_center_send.py",
    "scripts/xlsx_augment_sheets.py",
    "scripts/build_aegis_3sheet_workbook.py",
    # reconciler has positional reads that are guarded by header lookup
    "scripts/aegis_final_reconciler.py",
    # wave_regression has legacy A-check paths that use row[0]/row[1]
    "backend/research/wave_regression.py",
    # multi_layer has header-lookup already applied
    "backend/research/multi_layer",
    # Pre-existing tech debt · tracked separately for refactor · not gated by this rule
    "backend/delivery/outcome_ledger.py",
    "backend/delivery/telegram/detail_xlsx.py",
    "backend/research/lifecycle_stabilization.py",
    "backend/research/mr_evidence_layer.py",
}

_POSITIONAL_PATTERNS = [
    re.compile(r"row\[\s*[0-9]+\s*\]"),
    re.compile(r"\.cell\([^,]+,\s*[0-9]{2,}\)"),  # cell(r, N) where N >= 10
]


def _is_whitelisted(rel_path: str) -> bool:
    for w in _WHITELIST:
        if rel_path == w or rel_path.startswith(w + "/") or rel_path.startswith(w.replace("/", "\\") + "\\"):
            return True
    return False


def _scan_file(fp: Path):
    text = fp.read_text(encoding="utf-8", errors="replace")
    violations = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # Skip comments and docstrings-ish lines
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue
        for pat in _POSITIONAL_PATTERNS:
            if pat.search(line):
                violations.append((i, line.strip()[:100]))
    return violations


def test_no_positional_xlsx_reads_in_new_delivery_code():
    """S8 · new code in backend/delivery/ and backend/research/ must not
    use positional column reads. Enforces header-name access via resolvers."""
    scanned = []
    for base in ("backend/delivery", "backend/research"):
        base_dir = _ROOT / base
        if not base_dir.exists():
            continue
        for fp in base_dir.rglob("*.py"):
            rel = str(fp.relative_to(_ROOT)).replace("\\", "/")
            if _is_whitelisted(rel):
                continue
            v = _scan_file(fp)
            if v:
                scanned.append((rel, v))
    # Report first 5 violations for actionable output
    assert not scanned, (
        f"Positional XLSX reads found in {len(scanned)} file(s). "
        f"Use header-name resolvers (_row_val / _cell_val / _resolve_col). "
        f"First violations: " +
        " · ".join(f"{f}:{v[0][0]} `{v[0][1]}`" for f, v in scanned[:5])
    )

"""AEGIS · STANDARDS · every workbook sheet lookup must know the current names.

CEO 2026-09-07 · "make bulletproof".

THE CLASS OF BUG THIS EXISTS TO KILL
------------------------------------
The five-sheet rename (01_Portfolio -> R2, 03_Exit_History -> EXIT) broke
consumers one at a time, over three separate rounds, because each carried
its OWN private sheet-name lookup:

  round 1  aegis_final_reconciler, emit_provenance_companion,
           portfolio_exit_overlap_classifier, produce_visual_signoff
  round 2  stress_regime, crash_resilience, wave_regression (jargon check),
           r2_lifecycle_replay_e2e
  round 3  wave_regression A19, A22 and A23 · three MORE lookups in the
           same file that round 2 missed · which blocked USA delivery on
           17 phantom "silently lost" tickers

Fixing them individually is whack-a-mole: the next rename repeats it. This
test fails the build if ANY live lookup enumerates a legacy sheet name
without also listing the current one, so a stale consumer is caught at
test time rather than by a blocked delivery.

If a lookup is deliberately legacy-only (an archive reader, a migration),
name it in ALLOWED_LEGACY_ONLY with the reason.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Legacy name -> the current name that MUST appear alongside it.
REQUIRED_PAIRS = {
    "03_Exit_History": "EXIT",
    "Exit History (90d)": "EXIT",
    "01_Portfolio": "R2",
    "02_Today_Momentum": "MOMENTUM",
}

SCAN_DIRS = ("backend", "scripts", "usa", "india", "nexaquant")

# Files that legitimately mention a legacy name without the new one.
ALLOWED_LEGACY_ONLY = {
    # Declares the legacy contract shape itself · the aliases that pair
    # them live a few lines below in the same module.
    "backend/delivery/xlsx_contract.py",
    # Sheet-builder modules whose own `sheet_name` is the legacy tab they
    # build · these builders are retained but no longer emitted.
    "backend/delivery/sheets/composite_signals_sheet.py",
    "backend/delivery/sheets/health_cockpit_sheet.py",
    "backend/delivery/sheets/investments_sheet.py",
    "backend/delivery/sheets/r1_advisory_sheet.py",
    # The five-sheet reader's LEGACY_MAP and the audit's forbidden-list
    # exist precisely to name the old tabs.
    "backend/delivery/five_sheet_reader.py",
    "scripts/audit_five_sheet_workbook.py",
    # Row-offset table keyed by legacy layout · the alias resolution that
    # feeds it already includes the new names.
    "backend/delivery/xlsx_validator.py",
    # DEAD legacy emitters · retained as the reference implementation the
    # five-sheet builders were derived from, but no longer called. Verified
    # unwired: _emit_today_momentum has no caller, and
    # build_usa_missing_sheets_from_registry is referenced by nothing but a
    # test allowlist. If either is ever re-wired it must be migrated first,
    # because it would add a sixth sheet and break the five-sheet contract.
    "scripts/build_aegis_3sheet_workbook.py",
    "scripts/build_usa_missing_sheets_from_registry.py",
}


def _live_lines(path: Path):
    """Yield (line_no, text) for non-comment, non-docstring-ish lines."""
    in_doc = False
    for i, raw in enumerate(path.read_text(encoding="utf-8",
                                           errors="replace").splitlines(), 1):
        t = raw.strip()
        # crude but sufficient triple-quote tracking
        if t.count('"""') == 1 or t.count("'''") == 1:
            in_doc = not in_doc
            continue
        if in_doc or t.startswith("#") or t.startswith('"""') or t.startswith("'''"):
            continue
        yield i, raw


def _python_files():
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in str(p) or "/tests/" in p.as_posix():
                continue
            yield p


def test_every_sheet_lookup_knows_the_current_names():
    """A live reference to a legacy sheet name must also list the current one.

    Scoped per-file: if a module mentions `03_Exit_History` anywhere in
    live code, `EXIT` must appear in that module too.
    """
    violations = []
    for p in _python_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel in ALLOWED_LEGACY_ONLY:
            continue
        live = list(_live_lines(p))
        if not live:
            continue
        body = "\n".join(t for _, t in live)
        # Resolving the sheet through the shared reader's constants is
        # BETTER than hardcoding the literal, so it satisfies the rule:
        # such a file tracks the contract automatically.
        uses_shared_reader = any(
            tok in body for tok in
            ("five_sheet_reader", "SHEET_EXIT", "SHEET_R2", "SHEET_MOMENTUM",
             "SHEET_DAILY", "SHEET_R1", "FIVE_SHEETS"))
        for legacy, current in REQUIRED_PAIRS.items():
            quoted = f'"{legacy}"'
            if quoted not in body:
                continue
            # Compliant if the current literal appears, or the file routes
            # through the shared reader.
            if f'"{current}"' in body or uses_shared_reader:
                continue
            line_no = next((i for i, t in live if quoted in t), 0)
            violations.append(
                f"{rel}:{line_no} looks up {legacy!r} but never mentions "
                f"{current!r} · this consumer is blind to the current layout")
    assert not violations, (
        "Stale workbook sheet lookups found. Each will silently read an "
        "EMPTY sheet under the current layout, which is worse than an "
        "error because it looks like a clean zero:\n  "
        + "\n  ".join(violations))


def test_required_pairs_match_the_delivery_contract():
    """The pairs above must track the real contract · not drift from it."""
    from backend.delivery.sheets.workbook_five import FIVE_SHEETS
    for current in set(REQUIRED_PAIRS.values()):
        assert current in FIVE_SHEETS, (
            f"{current!r} is not a current sheet · REQUIRED_PAIRS is stale")


def test_allowlist_entries_all_exist():
    """An allowlist entry for a deleted file would silently widen scope."""
    missing = [rel for rel in ALLOWED_LEGACY_ONLY
               if not (ROOT / rel).exists()]
    assert not missing, f"ALLOWED_LEGACY_ONLY references missing files: {missing}"

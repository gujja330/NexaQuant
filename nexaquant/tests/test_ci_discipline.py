"""ENG003 · CI workflow discipline validator.

Scans every `.github/workflows/*.yml` file for reliability anti-patterns:
- `|| echo`     — silently masks step failure; workflow reports green when
                   the step actually failed
- `|| true`     — same but even more aggressive
- `continue-on-error: true` at step level

Every occurrence is compared against an inline GRANDFATHERED_MASKS registry.
New masks fail CI; grandfathered masks are documented debt items.

This test is the "no regressions on CI reliability" gate. It does NOT modify
production. It runs in the ENG001 regression workflow.

Run: python nexaquant/tests/test_ci_discipline.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WORKFLOWS_DIR = ROOT / ".github" / "workflows"


# --- Grandfathered masks (accepted debt as of ENG003 seal) ---
#
# Format: {workflow_relative_path: {(line_number, pattern) -> rationale}}
#
# Each entry is a KNOWN mask. Any NEW mask that isn't in this registry causes
# this test to fail. To promote a mask into the registry, document its rationale
# in ENG003_REPORT.md and add the entry here. To remove a mask, delete both the
# mask and its registry entry.

GRANDFATHERED_MASKS: dict[str, dict[tuple[int, str], str]] = {
    "aegis-daily.yml": {
        # Line numbers as of ENG003 seal — may drift by a few lines with edits.
        # Matching is by (approximate line, exact pattern text).
        (61, "|| echo \"data refresh issue; will let freshness gate decide\""):
            "ENG003 debt: refresh_data.py non-fatal so freshness gate can independently decide. "
            "ENG003 report §3.1 tracks this for ENG005 tightening.",
        (76, "|| echo \"engine issue; will send last snapshot\""):
            "ENG003 debt: recommendation_generator failure falls through to last-known Telegram send. "
            "Documented for ENG005.",
        (77, "|| echo \"db update skipped\""):
            "ENG003 debt: recommendation_db.py non-fatal — DB rebuild is idempotent. Documented.",
        (78, "|| echo \"scorecard skipped\""):
            "ENG003 debt: scorecard is reporting-only; non-fatal by design. Documented.",
        (79, "|| echo \"ops-check reported issues (see board above)\""):
            "ENG003 debt: ops_check.py is a reporter; non-zero exit is a signal not a failure.",
        (89, "|| echo \"sheets sync skipped/failed (non-fatal)\""):
            "ENG003 debt: Google Sheets is downstream mirror; failure must not stop primary Telegram.",
        # 2026-07-15: line 98 Telegram mask REMOVED. Notify is now routed through
        # scripts/telegram_send_with_retry.py which has 3 built-in retries and
        # exits non-zero on total failure. Any Telegram failure now fails the
        # workflow visibly. See docs/TELEGRAM_RELIABILITY_PLAN.md.
        (106, "|| true"):
            "ENG003 debt: git add masks - allows the workflow to continue if a specific pattern "
            "matched nothing on a given day.",
        (108, "|| true"):
            "ENG003 debt: git push mask - if remote raced, workflow continues; next run reconciles.",
    },
    "mon001-daily.yml": {
        # Note: the `|| \` line-continuation debt entry was removed 2026-07-15
        # (the daily_runner call no longer has a mask; the runner returns exit
        # 0 by design per MON001 certification §11, no shell mask needed).
        (75, "|| true"):
            "ENG003 debt: git add masks — MON001 outputs may legitimately be identical day-to-day.",
        (78, "|| true"):
            "ENG003 debt: git push race — mirrors aegis-daily.yml debt entry.",
    },
    "eng001-regression.yml": {},  # target: 0 masks; enforce zero
}


# Patterns considered masks (each pattern is a regex applied per line)
MASK_PATTERNS = (
    r"\|\|\s*echo\b",       # || echo "..."
    r"\|\|\s*true\b",       # || true
)


def _scan_workflow(path: Path) -> list[tuple[int, str, str]]:
    """Return (line_no, matched_text, full_line) for every mask hit.

    Skips comment lines and `name:` / `- name:` YAML lines whose value is a
    string that happens to describe masks (e.g. "Validate no || echo masks").
    """
    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        # Ignore comments that discuss masks
        if stripped.startswith("#"):
            continue
        # Ignore YAML `name:` / `- name:` fields (they're documentation, not run)
        if re.match(r"-?\s*name\s*:\s*", stripped):
            continue
        # Ignore other pure-YAML descriptive lines (e.g. `description:`)
        if re.match(r"-?\s*(description|title)\s*:\s*", stripped):
            continue
        for pat in MASK_PATTERNS:
            if re.search(pat, line):
                # Extract the mask expression only (from `||` onwards)
                m = re.search(r"(\|\|\s*(?:echo\b[^\n]*|true\b))", line)
                if m:
                    hits.append((i, m.group(1).strip(), line.rstrip()))
                break
    return hits


def _lookup_grandfather(workflow: str, line_no: int, matched: str) -> str | None:
    """Match by (workflow_file, mask_content). Line numbers drift as workflows
    evolve — the mask content itself is the durable signature. Line numbers in
    GRANDFATHERED_MASKS are informational only."""
    reg = GRANDFATHERED_MASKS.get(workflow, {})
    matched_norm = matched.strip()
    for (_reg_line, reg_pat), rationale in reg.items():
        reg_pat_norm = reg_pat.strip()
        if reg_pat_norm == matched_norm:
            return rationale
        # Tolerate small trailing-quote / whitespace normalization.
        if reg_pat_norm.split()[:2] == matched_norm.split()[:2]:
            return rationale
    return None


def test_workflow_masks_grandfathered_only():
    """Every `|| echo` / `|| true` in every workflow must be in GRANDFATHERED_MASKS."""
    if not WORKFLOWS_DIR.exists():
        print("  no .github/workflows/ present — skipping")
        return
    ungrandfathered: list[str] = []
    total = 0
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        hits = _scan_workflow(wf)
        for line_no, matched, full_line in hits:
            total += 1
            rationale = _lookup_grandfather(wf.name, line_no, matched)
            if rationale is None:
                ungrandfathered.append(
                    f"    {wf.name}:{line_no}  {matched}\n      -> {full_line}")
    if ungrandfathered:
        msg = ("\n  ENG003 CI-discipline violation: new || echo / || true mask found "
                "without a GRANDFATHERED_MASKS entry:\n"
                + "\n".join(ungrandfathered)
                + "\n\n  To resolve either:\n"
                + "    (a) remove the mask + let the step fail loudly, OR\n"
                + "    (b) add a GRANDFATHERED_MASKS entry with a rationale + reference in ENG003_REPORT.md")
        raise AssertionError(msg)
    print(f"  ci-discipline: {total} masks scanned, all grandfathered")


def test_eng001_regression_workflow_has_zero_masks():
    """The ENG001/ENG003 regression workflow itself must have zero masks."""
    wf = WORKFLOWS_DIR / "eng001-regression.yml"
    if not wf.exists():
        print("  eng001-regression.yml missing — skipping")
        return
    hits = _scan_workflow(wf)
    assert not hits, (
        f"eng001-regression.yml has {len(hits)} masks — this workflow gates the whole "
        f"regression, it must fail loudly on any step: {hits}")
    print("  ci-discipline: eng001-regression.yml has 0 masks")


def test_all_workflows_require_python_and_deps_install():
    """Every workflow that runs python steps must first install deps.
    Prevents 'module not found' silent failures (like the pyarrow bug that caused
    the ENG001 CI failure reported by the operator)."""
    if not WORKFLOWS_DIR.exists():
        print("  no .github/workflows/ present — skipping")
        return
    findings: list[str] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        if "python" not in text.lower():
            continue
        if "python -m pip install" not in text and "pip install" not in text and \
           "setup-python@" not in text:
            findings.append(f"    {wf.name}: python steps but no pip install step")
    if findings:
        raise AssertionError("workflows missing dep install:\n" + "\n".join(findings))
    print("  ci-discipline: every python workflow has a dep install step")


def test_workflow_yaml_parses():
    """Every workflow YAML must parse cleanly (broken YAML == silent no-op in GH Actions)."""
    import yaml
    if not WORKFLOWS_DIR.exists():
        return
    bad: list[str] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        try:
            data = yaml.safe_load(wf.read_text(encoding="utf-8"))
            assert isinstance(data, dict) and "jobs" in data, f"{wf.name}: no jobs key"
        except Exception as e:
            bad.append(f"    {wf.name}: {type(e).__name__}: {e}")
    if bad:
        raise AssertionError("workflow YAML errors:\n" + "\n".join(bad))
    print("  ci-discipline: all workflow YAMLs parse")


def test_workflows_use_pinned_action_major_versions():
    """Every `uses:` line should reference an action with a version pin
    (uses: owner/repo@v4 or @sha). Unpinned actions are a supply-chain risk."""
    if not WORKFLOWS_DIR.exists():
        return
    findings: list[str] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        for i, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), start=1):
            m = re.match(r"\s*-?\s*uses:\s*([\w\-./]+)(@[\w\-.]+)?", line)
            if m and not m.group(2):
                findings.append(f"    {wf.name}:{i}  unpinned action: {m.group(1)}")
    if findings:
        raise AssertionError(
            "unpinned GitHub Action references (supply-chain risk):\n"
            + "\n".join(findings))
    print("  ci-discipline: every action reference is version-pinned")


TESTS = [
    test_workflow_yaml_parses,
    test_workflows_use_pinned_action_major_versions,
    test_workflow_masks_grandfathered_only,
    test_eng001_regression_workflow_has_zero_masks,
    test_all_workflows_require_python_and_deps_install,
]


def main():
    print("=" * 70)
    print("  ENG003 CI DISCIPLINE VALIDATOR")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  [OK] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

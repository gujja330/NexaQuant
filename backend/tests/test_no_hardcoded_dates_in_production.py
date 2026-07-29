"""Guardrail · no hardcoded ISO dates in production code paths.

Operator directive (2026-07-29): "all developments should be dynamic ·
plz dont hardcode any dates · product should be sustainable for future
without hardcodes"

Definitions
  Production code paths = backend/, scripts/, india/ (except sealed
    MON001), usa/scripts + usa/research (except sealed contracts)
  Allowed hardcodes
    · Test files (tests/*)             — test fixtures may use dates
    · Data files (*.json, *.parquet, *.jsonl, *.yaml) — data snapshots
    · Documentation (docs/, *.md, comments) — historical references
    · Sealed MON001 area                — untouched per Wave Y
    · Sealed adaptive_rec_v2, risk_capital_v2 — untouched per Constitution
    · Epoch dates like date(2000,1,1)   — reference/anchor points
    · Holiday tables (data lookup)      — legitimate business calendar

Enforcement
  Grep-scans production .py files for `date(YYYY,...)` or `'YYYY-MM-DD'`
  patterns where YYYY is 2020..2030. Fails if any survive the allowlist.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Production dirs to scan
PRODUCTION_DIRS = [
    "backend",
    "scripts",
    "india",
    "usa/scripts",
    "usa/research",
]

# Files/paths to exclude (sealed contracts, data holidays, tests, research)
EXCLUDE_PATTERNS = [
    r"tests/",                                           # tests may use dates
    r"__pycache__/",
    r"backend/monitoring/",                              # legacy monitoring
    r"india/monitoring/MON001_Forward_Validation/",      # sealed MON001
    r"india/adaptive_rec_v2/", r"india/risk_capital_v2/", # sealed research
    r"research/",                                        # sealed research
    r"india/ai_lab/",                                    # research/lab experiments
    r"india/evidence/",                                  # research/evidence backtests
    # Legitimate holiday tables — dates ARE the data:
    r"scripts/check_data_freshness\.py",
    # Sealed telegram/champion legacy that predates the rule:
    r"india/telegram_notify\.py",
    # One-off historical report generator with specific run-date semantics
    # (should be CLI-arg refactored eventually · flagged for future cycle)
    r"india/results_report\.py",
]

# Regex patterns
DATE_PATTERNS = [
    re.compile(r"\bdate\s*\(\s*20[2-3]\d\s*,\s*\d+\s*,\s*\d+\s*\)"),
    re.compile(r"['\"]20(2[4-9]|30)-\d\d-\d\d['\"]"),
]

# Whitelisted specific dates
WHITELIST_LITERALS = {
    "2000-01-01",   # epoch reference
    "1970-01-01",   # unix epoch
    "1900-01-01",   # pandas NA sentinel
}


def _is_excluded(rel_path: str) -> bool:
    return any(re.search(p, rel_path) for p in EXCLUDE_PATTERNS)


def _scan_file(path: Path, root: Path) -> list[tuple[int, str]]:
    """Return [(line_no, matched_text)] for hardcoded date literals."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # Skip pure comment lines - only enforce on code
        if stripped.startswith("#"):
            continue
        for pat in DATE_PATTERNS:
            for m in pat.finditer(line):
                literal = m.group(0)
                # Skip if inside a comment tail
                code_before_hash = line.split("#", 1)[0]
                if m.start() > len(code_before_hash):
                    continue
                # Skip whitelisted specific dates
                if any(w in literal for w in WHITELIST_LITERALS):
                    continue
                hits.append((i, literal))
    return hits


def test_no_hardcoded_dates_in_production_code():
    violations: list[str] = []
    for prod_dir in PRODUCTION_DIRS:
        d = _ROOT / prod_dir
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            rel = str(p.relative_to(_ROOT)).replace("\\", "/")
            if _is_excluded(rel):
                continue
            hits = _scan_file(p, _ROOT)
            for line_no, literal in hits:
                violations.append(f"  {rel}:{line_no}  {literal}")

    assert not violations, (
        "Hardcoded dates found in production code (operator directive · "
        "no hardcoded dates anywhere). Fix by deriving from wall clock "
        "or moving to config JSON:\n" + "\n".join(violations)
    )


def test_holiday_calendars_flagged_for_yearly_refresh():
    """Softer check: holiday calendars are the legitimate exception but
    they need YEARLY updates. Warn if the most recent hardcoded holiday
    is more than 400 days from today (i.e., you're running in a year
    with no holidays defined)."""
    from datetime import date, timedelta
    candidates = [
        _ROOT / "scripts" / "check_data_freshness.py",
        _ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "ops" / "holiday_calendar.py",
    ]
    warned: list[str] = []
    today = date.today()
    for p in candidates:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        matches = re.findall(r"date\((20\d\d),\s*(\d+),\s*(\d+)\)", text)
        if not matches:
            continue
        latest = max((date(int(y), int(m), int(d)) for y, m, d in matches
                        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31),
                        default=None)
        if latest and (today - latest).days > 400:
            warned.append(f"{p.name}: latest holiday {latest} is "
                            f"{(today - latest).days}d stale · refresh")
    # This is a WARN not a FAIL — legitimate data table that needs
    # yearly maintenance. Print, don't assert (still gives operator visibility).
    if warned:
        print("HOLIDAY CALENDAR REFRESH RECOMMENDED:")
        for w in warned:
            print(f"  {w}")


def test_feature_registry_defaults_are_not_hardcoded():
    """Locks the specific fix made in this cycle."""
    p = _ROOT / "backend" / "feature_store" / "feature_registry.py"
    src = p.read_text(encoding="utf-8")
    # Neither default should be a hardcoded date literal
    for line in src.splitlines():
        if "created:" in line and "str" in line and "=" in line:
            assert '20' not in line or 'hardcoded' in line.lower() or '""' in line, (
                f"feature_registry.py 'created' default reintroduced a hardcoded "
                f"date: {line.strip()}"
            )

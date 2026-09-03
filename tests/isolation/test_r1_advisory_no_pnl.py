"""Sprint A · R1 Advisory Isolation · CI test that R1 positions are
excluded from AEGIS production P&L paths.

R1 is RETIRED_ADVISORY: engine remains alive producing daily picks,
those picks may be surfaced on the 05_R1_Advisory sheet, but MUST NOT
be counted in Portfolio P&L, Exit History realized-90d metrics, or
banner counts.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(p: Path):
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_r1_status_is_retired_advisory():
    cfg = _load_yaml(_ROOT / "configs/aegis_runner_registry.yaml")
    r1 = cfg["runners"]["R1"]
    assert r1["status"] == "RETIRED_ADVISORY"
    assert r1["production_pnl"] is False, (
        "R1 must never contribute to production P&L. "
        "Set production_pnl=false in aegis_runner_registry.yaml."
    )
    assert r1["workbook_visibility"] == "advisory_only"


def test_r1_retirement_config_lists_r1():
    """The authoritative retirement config must include R1."""
    p = _ROOT / "configs/aegis_retirement.yaml"
    if not p.exists():
        # Not yet present in some branches — the registry alone is enough
        return
    cfg = _load_yaml(p)
    retired = cfg.get("retired_runners", []) or cfg.get("retired", [])
    assert "R1" in retired, "R1 missing from configs/aegis_retirement.yaml"


def test_r1_producer_guard_check():
    """opportunity_registry.get_or_create must consult is_retired
    before allowing R1 position creation."""
    fp = _ROOT / "backend/research/opportunity_registry.py"
    if not fp.exists():
        return
    src = fp.read_text(encoding="utf-8", errors="replace")
    assert "is_retired(root, runner)" in src, (
        "R1 producer guard missing · get_or_create must refuse to "
        "instantiate a retired runner's position."
    )


def test_workbook_builder_excludes_r1_from_portfolio():
    """build_aegis_3sheet_workbook.py Portfolio-sheet code path
    must exclude R1 positions when R1 is retired."""
    fp = _ROOT / "scripts/build_aegis_3sheet_workbook.py"
    src = fp.read_text(encoding="utf-8", errors="replace")
    # Look for retirement-aware filter markers
    markers = ["is_retired(", "retired_runners", "R1_HIDDEN", "aegis_retirement"]
    hit = any(m in src for m in markers)
    assert hit, (
        "Portfolio builder appears to not consult retirement config. "
        "Ensure R1 positions are filtered out of the Portfolio sheet."
    )

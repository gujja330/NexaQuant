"""Sprint A · Composite layer isolation · CI test that composite code
cannot write to Registry or Exit History or any production P&L path."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

_FORBIDDEN_PATHS = [
    "reports/research/opportunity_registry",  # Registry JSONL
    "reports/telegram/aegis_history",         # workbook history files
    "reports/telegram/aegis_india_",          # dated per-market files
    "reports/telegram/aegis_usa_",
    "configs/aegis_retirement",
    "configs/ensemble_weights_adaptive",
]

_FORBIDDEN_CALLS = [
    "oreg.get_or_create", "oreg.close", "oreg.reject",
    "opportunity_registry.get_or_create",
    "opportunity_registry.close",
    "opportunity_registry.reject",
]


def _composite_source_files():
    d = _ROOT / "backend" / "recommendation" / "composite"
    if d.exists():
        for fp in d.rglob("*.py"):
            yield fp


def test_composite_never_writes_to_registry_or_production():
    violations = []
    for fp in _composite_source_files():
        text = fp.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"): continue
            for path in _FORBIDDEN_PATHS:
                if path in line:
                    violations.append(f"{fp.relative_to(_ROOT)}:{line_num} · {path}")
            for call in _FORBIDDEN_CALLS:
                if call in line:
                    violations.append(f"{fp.relative_to(_ROOT)}:{line_num} · calls {call}")
    assert not violations, (
        "Composite layer references forbidden path or Registry writer:\n"
        + "\n".join(violations[:10])
    )

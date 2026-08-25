# tests/research/test_alpha_report_and_ceo_summary.py
"""AEGIS · Sprint M · tests for Consolidated Alpha Report + CEO Daily Summary
+ lifecycle tightening (EXIT is the ONE terminal word)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest


# ═════════════════════════════════════════════════════════════════
# Lifecycle · canonical 4-state set · CEO tightening
# ═════════════════════════════════════════════════════════════════
class TestLifecycleCanonical:

    def test_canonical_states_are_four(self):
        from backend.research.lifecycle_stabilization import VALID_STATES
        # NEW / ACTIVE / ACTIVE+ / EXIT · exactly 4 canonical
        assert VALID_STATES == {"NEW", "ACTIVE", "ACTIVE+", "EXIT"}
        # CLOSED is NOT in canonical (legacy)
        assert "CLOSED" not in VALID_STATES

    def test_canonicalize_maps_closed_to_exit(self):
        from backend.research.lifecycle_stabilization import canonicalize_state
        assert canonicalize_state("CLOSED") == "EXIT"
        assert canonicalize_state("closed") == "EXIT"
        assert canonicalize_state("EXIT") == "EXIT"

    def test_canonicalize_maps_hold_to_active(self):
        from backend.research.lifecycle_stabilization import canonicalize_state
        assert canonicalize_state("HOLD") == "ACTIVE"

    def test_canonicalize_maps_rotated_sameday_to_exit(self):
        from backend.research.lifecycle_stabilization import canonicalize_state
        assert canonicalize_state("ROTATED_SAMEDAY") == "EXIT"

    def test_canonicalize_leaves_valid_alone(self):
        from backend.research.lifecycle_stabilization import canonicalize_state
        for s in ("NEW", "ACTIVE", "ACTIVE+", "EXIT"):
            assert canonicalize_state(s) == s

    def test_legacy_states_tolerated_but_not_canonical(self):
        from backend.research.lifecycle_stabilization import (
            LEGACY_STATES, VALID_STATES)
        # These CAN exist in Registry for backwards-compat
        for s in ("CLOSED", "HOLD", "ROTATED_SAMEDAY"):
            assert s in LEGACY_STATES
            assert s not in VALID_STATES

    def test_forbidden_states_never_added(self):
        from backend.research.lifecycle_stabilization import (
            VALID_STATES, LEGACY_STATES)
        # PROTECT/REVIEW/TRAIL/TAKE_PROFIT are DECISION MODIFIERS, not
        # lifecycle states · must NEVER be in either set.
        for forbidden in ("PROTECT", "REVIEW", "TRAIL", "TAKE_PROFIT"):
            assert forbidden not in VALID_STATES
            assert forbidden not in LEGACY_STATES


# ═════════════════════════════════════════════════════════════════
# Consolidated Alpha Report
# ═════════════════════════════════════════════════════════════════
class TestAlphaReport:

    def test_empty_root_still_produces_report(self, tmp_path):
        from backend.research import aegis_alpha_report as _ar
        rep = _ar.compute(tmp_path, "india")
        assert rep.market == "india"
        assert isinstance(rep.metrics, dict)
        # All 25 CEO keys must be populated (may be empty values)
        for k in _ar.METRIC_KEYS:
            assert k in rep.metrics, f"missing metric key {k}"

    def test_25_metric_keys(self):
        from backend.research.aegis_alpha_report import METRIC_KEYS
        assert len(METRIC_KEYS) == 25

    def test_emit_writes_json_and_md(self, tmp_path):
        from backend.research import aegis_alpha_report as _ar
        rep = _ar.compute(tmp_path, "india")
        j = _ar.emit(tmp_path, rep)
        m = _ar.emit_markdown(tmp_path, rep)
        assert j.exists()
        assert m.exists()
        content = m.read_text(encoding="utf-8")
        assert "AEGIS Alpha Report" in content
        assert "Win rate" in content

    def test_summary_line_format(self, tmp_path):
        from backend.research import aegis_alpha_report as _ar
        rep = _ar.compute(tmp_path, "india")
        s = _ar.summary_line(rep)
        assert "alpha_report" in s
        assert "state=" in s
        assert "win_rate=" in s


# ═════════════════════════════════════════════════════════════════
# CEO Daily Summary
# ═════════════════════════════════════════════════════════════════
class TestCEODailySummary:

    def test_empty_root_produces_5_section_shell(self, tmp_path):
        from backend.delivery import ceo_daily_summary as _cd
        s = _cd.compute(tmp_path, "india")
        md = _cd.render_markdown(s)
        # 5 sections must all appear
        assert "🆕 NEW" in md
        assert "✅ EXISTING" in md
        assert "⚠  RISK" in md
        assert "❌ LOSSES" in md
        assert "🏆 WINNERS" in md

    def test_emit_writes_md_and_json(self, tmp_path):
        from backend.delivery import ceo_daily_summary as _cd
        s = _cd.compute(tmp_path, "india")
        md_p = _cd.emit(tmp_path, s)
        assert md_p.exists()
        assert md_p.suffix == ".md"
        jp = md_p.parent / f"ceo_daily_summary_{s.market}.json"
        assert jp.exists()

    def test_summary_line(self, tmp_path):
        from backend.delivery import ceo_daily_summary as _cd
        s = _cd.compute(tmp_path, "india")
        line = _cd.summary_line(s)
        assert "ceo_daily_summary" in line

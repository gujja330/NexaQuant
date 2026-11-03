"""The operator hard-locked Command Center format.

CEO 2026-11-03 · Phase B4. Two tests asserted that the message carries an
"AI PERFORMANCE SCORECARD" and a "WHAT DROVE TODAY'S DECISIONS" block.
Both renderers exist and both work - and both have ZERO callers. The
`sections` list in `render_command_center_message` has 12 entries under a
comment reading "Operator hard-locked format · Format spec §3", and
neither is among them. Fourteen functions in that module are orphaned the
same way.

The exclusion is deliberate, so this file pins the locked format instead
of demanding sections the lock omits: the 12 sections, their order, the
character-budget behaviour, deterministic output, and - the part that
matters for regression - that none of the orphaned renderers can appear
in the message without someone editing the `sections` list.

A format change needs approval and before/after budget measurements,
because the assembler DROPS whole sections that do not fit: adding one
section can silently evict another.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import backend.delivery.telegram.command_center as cc

_REPO = Path(__file__).resolve().parents[2]

#: The locked order, as the `sections` list declares it.
LOCKED_SECTIONS = (
    "header", "ceo_call", "runner_experiment", "runner_comparison",
    "rotations", "new_buys", "r2_holds", "exits", "r1_orphans",
    "what_changed", "risk_pulse", "footer",
)

#: Renderers present in the module but not wired into `sections`. Listed so
#: a future edit that wires one in has to come past this test and say so.
ORPHANED_RENDERERS = (
    "_performance_summary", "_runner_attribution_table", "_research_tail",
    "_evolution_summary", "_ai_scorecard_line", "_attribution_top",
    "_intraday_hint", "_runner2_exclusive", "_runner1_agreement_summary",
    "_research_platform_block", "_head_to_head_block",
    "_backtest_snapshot_block",
)


def _payload(market="india", n_recs=0, **extra):
    asof = date.today().isoformat()
    p = {
        "asof": asof, "market": market,
        "run_utc": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
        "ceo_summary": {"recommended_action": "Test",
                        "market_regime": "unknown", "actionable_count": 0,
                        "rotations_count": 0, "top_opportunity": None,
                        "top_risk": None},
        "recommendations": [
            {"ticker": "T%03d" % i, "action": "BUY", "confidence": 0.5,
             "rank": i + 1, "lifecycle_state": "ACTIVE"}
            for i in range(n_recs)],
    }
    p.update(extra)
    return p


def _source() -> str:
    """Module source with comment lines and comment tails removed."""
    out = []
    p = Path(cc.__file__)
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("#"):
            continue
        out.append(line.split("#", 1)[0] if "#" in line else line)
    return "\n".join(out)


def _declared_sections() -> list:
    """Section names from the `sections = [...]` literal, in order."""
    src = _source()
    i = src.index("sections = [")
    j = src.index("]", i)
    return re.findall(r'\(\s*"([a-z0-9_]+)"', src[i:j])


class TestTheTwelveSections:
    def test_there_are_exactly_twelve(self):
        assert len(_declared_sections()) == 12

    def test_the_order_is_the_locked_order(self):
        assert tuple(_declared_sections()) == LOCKED_SECTIONS

    def test_the_footer_is_last(self):
        """The assembler reserves the footer's budget before anything else."""
        assert _declared_sections()[-1] == "footer"

    def test_the_header_is_first(self):
        assert _declared_sections()[0] == "header"


class TestOrphanedRenderersStayOut:
    @pytest.mark.parametrize("name", ORPHANED_RENDERERS)
    def test_the_renderer_still_exists(self, name):
        """They are dead, not deleted · the distinction is the point."""
        assert callable(getattr(cc, name, None)), name

    @pytest.mark.parametrize("name", ORPHANED_RENDERERS)
    def test_it_is_not_called_anywhere_in_the_module(self, name):
        src = _source()
        calls = src.count("%s(" % name)
        assert calls == 1, (
            "%s is called %d times · wiring an orphaned section into the "
            "locked format needs an approved format change with before/"
            "after character-budget measurements, because the assembler "
            "drops whole sections that do not fit" % (name, calls - 1))

    def test_the_scorecard_block_is_absent_from_the_message(self):
        msg = cc.render_command_center_message(
            _payload(ai_scorecard={"overall_score": 84.0, "overall_stars": 4,
                                   "verdict": "institutional_grade",
                                   "n_trades": 1060}), "india")
        assert "AI PERFORMANCE SCORECARD" not in msg

    def test_the_attribution_block_is_absent_from_the_message(self):
        msg = cc.render_command_center_message(
            _payload(attribution_summary={
                "dominant_drivers": {"Momentum": 4},
                "avg_sector_share_pct": 12.5,
                "sector_engine_measurably_active": True}), "india")
        assert "WHAT DROVE TODAY'S DECISIONS" not in msg

    def test_an_orphan_payload_key_cannot_grow_the_message(self):
        """Supplying the data for an excluded section changes nothing."""
        bare = cc.render_command_center_message(_payload(), "india")
        loaded = cc.render_command_center_message(
            _payload(ai_scorecard={"overall_score": 84.0, "overall_stars": 4,
                                   "verdict": "x", "n_trades": 7},
                     attribution_summary={"dominant_drivers": {"M": 1},
                                          "avg_sector_share_pct": 1.0}),
            "india")
        assert bare == loaded


class TestCharacterBudget:
    def test_the_message_respects_an_explicit_budget(self):
        for budget in (400, 1200, 4000):
            msg = cc.render_command_center_message(
                _payload(n_recs=40), "india", budget=budget)
            assert len(msg) <= budget, (len(msg), budget)

    def test_a_tighter_budget_never_produces_a_longer_message(self):
        lens = [len(cc.render_command_center_message(
            _payload(n_recs=40), "india", budget=b))
            for b in (400, 800, 1600, 3200)]
        assert lens == sorted(lens), lens

    def test_the_footer_survives_the_tightest_budget(self):
        """It is pre-reserved · a message with no provenance is worse than
        a truncated one."""
        msg = cc.render_command_center_message(
            _payload(n_recs=60), "india", budget=500)
        assert "Advisory only" in msg or "AEGIS" in msg

    def test_sections_are_dropped_whole_not_truncated_mid_line(self):
        msg = cc.render_command_center_message(
            _payload(n_recs=60), "india", budget=900)
        assert not msg.endswith("…")
        assert msg == msg.strip()


class TestDeterminism:
    def test_two_renders_of_one_payload_are_identical(self):
        p = _payload(n_recs=12)
        assert (cc.render_command_center_message(p, "india")
                == cc.render_command_center_message(p, "india"))

    def test_rendering_does_not_mutate_the_payload(self):
        import copy
        p = _payload(n_recs=12)
        before = copy.deepcopy(p)
        cc.render_command_center_message(p, "india")
        assert p == before

    def test_both_markets_render_without_error(self):
        for m in ("india", "usa"):
            msg = cc.render_command_center_message(_payload(m, n_recs=5), m)
            assert msg and isinstance(msg, str)

    def test_an_empty_recommendation_list_still_renders(self):
        msg = cc.render_command_center_message(_payload(n_recs=0), "india")
        assert msg.strip()


class TestNoLegacySourcesInTheLockedPath:
    def test_the_renderer_does_not_read_the_legacy_csv(self):
        """Covered by the v3 lock contract · asserted here too, because
        this is the file that decides what ships."""
        assert "aegis_today.csv" not in _source()

    def test_the_renderer_reads_the_ssot(self):
        assert "recommendations.json" in _source()

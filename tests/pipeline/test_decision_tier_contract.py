"""One canonical status -> tier mapping, with unknowns held unfavourable.

CEO 2026-11-03 · Phase B5. `telegram_command_center_send.py` sorted rows
with its own tier keys - closed, exit, new, strong_buy, buy, hold - while
configs/decision_colors.yaml defined only new (1), active (2) and exit (3).
Four of the six matched nothing and fell to rank 99, so EXIT sorted ABOVE
every held position and STRONG BUY / BUY / HOLD / artifacts collapsed into
one bucket, inverting the order the config states.

These tests pin every supported status, the unknown-status contract, and
the invariant that the renderer no longer carries a private copy. The
hard-locked decision vocabulary [NEW, ACTIVE, ACTIVE+, EXIT] is unchanged -
this maps richer wire statuses ONTO those tiers.

tmp_path-isolated except where a test says it reads the repo config.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.delivery import decision_tiers as DT

_REPO = Path(__file__).resolve().parents[2]

HELD = ("ACTIVE", "ACTIVE+", "HOLD", "BUY", "STRONG BUY", "STRONG_BUY",
        "ACCUMULATE", "ADD", "PROTECT", "TIGHTEN", "WATCH", "PROVISIONAL")
TERMINAL = ("EXIT", "SELL", "STRONG SELL", "STRONG_SELL", "REDUCE",
            "CLOSED", "SKIP", "ARTIFACT", "IGNORE", "IMMEDIATE")


def _cfg(tmp_path, body: str) -> Path:
    p = tmp_path / "configs" / "decision_colors.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    DT._CACHE.clear()
    return tmp_path


_MINIMAL = """
tiers:
  new:    {tier_rank: 1}
  active: {tier_rank: 2}
  exit:   {tier_rank: 3}
status_tiers:
  NEW:  new
  BUY:  active
  SELL: exit
unknown_tier_rank: 99
"""


class TestEverySupportedStatus:
    def test_new_is_the_first_tier(self):
        assert DT.tier_for_status(_REPO, "NEW") == ("new", True)
        assert DT.tier_rank(_REPO, "NEW") == 1

    @pytest.mark.parametrize("s", HELD)
    def test_every_held_status_maps_to_active(self, s):
        key, known = DT.tier_for_status(_REPO, s)
        assert known is True, "%s must be mapped" % s
        assert key == "active"
        assert DT.tier_rank(_REPO, s) == 2

    @pytest.mark.parametrize("s", TERMINAL)
    def test_every_terminal_status_maps_to_exit(self, s):
        key, known = DT.tier_for_status(_REPO, s)
        assert known is True, "%s must be mapped" % s
        assert key == "exit"
        assert DT.tier_rank(_REPO, s) == 3

    @pytest.mark.parametrize("s", ("buy", " Buy ", "bUy"))
    def test_matching_is_case_and_whitespace_insensitive(self, s):
        assert DT.tier_rank(_REPO, s) == 2

    def test_the_locked_vocabulary_is_all_covered(self):
        """[NEW, ACTIVE, ACTIVE+, EXIT] · the hard lock."""
        for s in ("NEW", "ACTIVE", "ACTIVE+", "EXIT"):
            _, known = DT.tier_for_status(_REPO, s)
            assert known is True, s

    def test_no_status_points_at_a_tier_that_does_not_exist(self):
        """An orphan target is how `buy` resolved to nothing before."""
        assert DT.audit(_REPO)["orphan_targets"] == []


class TestTheOrderingIsTheConfiguredOrdering:
    def test_held_sorts_before_terminal(self):
        """The defect inverted this · EXIT used to sort first."""
        assert DT.tier_rank(_REPO, "BUY") < DT.tier_rank(_REPO, "EXIT")
        assert DT.tier_rank(_REPO, "HOLD") < DT.tier_rank(_REPO, "SELL")

    def test_new_sorts_before_held_and_terminal(self):
        assert (DT.tier_rank(_REPO, "NEW")
                < DT.tier_rank(_REPO, "ACTIVE")
                < DT.tier_rank(_REPO, "EXIT"))

    def test_buy_and_hold_are_no_longer_at_the_unknown_rank(self):
        """The specific regression: both were 99."""
        u = DT.unknown_rank(_REPO)
        assert DT.tier_rank(_REPO, "BUY") != u
        assert DT.tier_rank(_REPO, "HOLD") != u
        assert DT.tier_rank(_REPO, "STRONG BUY") != u
        assert DT.tier_rank(_REPO, "ARTIFACT") != u

    def test_strong_buy_and_buy_share_the_held_tier(self):
        """Three colours, by operator directive · not six."""
        assert DT.tier_rank(_REPO, "STRONG BUY") == DT.tier_rank(_REPO, "BUY")


class TestUnknownIsNeverFavourable:
    def test_an_unmapped_status_is_reported_as_unknown(self, tmp_path):
        root = _cfg(tmp_path, _MINIMAL)
        assert DT.tier_for_status(root, "MYSTERY") == (DT.UNKNOWN_TIER, False)

    def test_an_unmapped_status_sorts_after_every_real_tier(self, tmp_path):
        root = _cfg(tmp_path, _MINIMAL)
        u = DT.tier_rank(root, "MYSTERY")
        for s in ("NEW", "BUY", "SELL"):
            assert u > DT.tier_rank(root, s), s

    def test_the_repo_config_keeps_unknown_above_every_tier(self):
        """A tier_rank raised past 99 would make UNKNOWN favourable."""
        a = DT.audit(_REPO)
        assert all(r < a["unknown_tier_rank"] for r in a["tiers"].values()), a

    @pytest.mark.parametrize("s", ("", None, "   "))
    def test_an_empty_status_is_unknown_not_a_default_tier(self, s):
        key, known = DT.tier_for_status(_REPO, s)
        assert (key, known) == (DT.UNKNOWN_TIER, False)
        assert DT.tier_rank(_REPO, s) == DT.unknown_rank(_REPO)

    def test_a_status_pointing_at_a_missing_tier_is_unknown(self, tmp_path):
        root = _cfg(tmp_path, """
tiers:
  active: {tier_rank: 2}
status_tiers:
  BUY:  active
  WEIRD: nonexistent_tier
unknown_tier_rank: 99
""")
        assert DT.tier_for_status(root, "WEIRD") == (DT.UNKNOWN_TIER, False)
        assert DT.tier_rank(root, "WEIRD") == 99
        assert DT.audit(root)["orphan_targets"] == ["nonexistent_tier"]

    def test_a_non_numeric_tier_rank_falls_to_unknown(self, tmp_path):
        root = _cfg(tmp_path, """
tiers:
  active: {tier_rank: "not a number"}
status_tiers:
  BUY: active
unknown_tier_rank: 99
""")
        assert DT.tier_rank(root, "BUY") == 99

    def test_a_missing_config_does_not_crash_and_is_unfavourable(self, tmp_path):
        DT._CACHE.clear()
        assert DT.tier_rank(tmp_path, "BUY") == DT.DEFAULT_UNKNOWN_RANK
        assert DT.tier_for_status(tmp_path, "BUY") == (DT.UNKNOWN_TIER, False)

    def test_a_malformed_config_does_not_crash(self, tmp_path):
        root = _cfg(tmp_path, "tiers: [this is not a mapping")
        assert DT.tier_rank(root, "BUY") == DT.DEFAULT_UNKNOWN_RANK


class TestUnmappedDiagnostic:
    def test_it_names_the_gaps(self, tmp_path):
        root = _cfg(tmp_path, _MINIMAL)
        gaps = DT.unmapped_statuses(root, ["BUY", "HOLD", "ACCUMULATE", "NEW"])
        assert gaps == ["ACCUMULATE", "HOLD"]

    def test_the_repo_config_covers_every_status_the_renderer_emits(self):
        """The statuses the sort block can actually produce.

        This is the check that would have caught the original defect: the
        renderer's own branches yield ARTIFACT, EXIT, NEW and whatever
        `status` holds, and four of those used to be unmapped.
        """
        emitted = ["ARTIFACT", "EXIT", "NEW", "STRONG BUY", "BUY",
                   "ACCUMULATE", "SELL", "REDUCE", "HOLD", "ACTIVE",
                   "ACTIVE+", "CLOSED"]
        assert DT.unmapped_statuses(_REPO, emitted) == []

    def test_an_empty_probe_reports_no_gaps(self):
        assert DT.unmapped_statuses(_REPO, []) == []
        assert DT.unmapped_statuses(_REPO, None) == []


class TestTheRendererHasNoPrivateCopy:
    @staticmethod
    def _code_only(path: Path) -> str:
        out = []
        for line in path.read_text(encoding="utf-8",
                                   errors="replace").splitlines():
            if line.strip().startswith("#"):
                continue
            out.append(line.split("#", 1)[0] if "#" in line else line)
        return "\n".join(out)

    def test_the_sort_delegates_to_the_canonical_owner(self):
        src = self._code_only(_REPO / "scripts/telegram_command_center_send.py")
        assert "_canonical_tier_rank" in src
        assert "decision_tiers" in src

    def test_the_old_private_tier_keys_are_gone(self):
        src = self._code_only(_REPO / "scripts/telegram_command_center_send.py")
        for dead in ('tier = "strong_buy"', 'tier = "buy"',
                     'tier = "hold"', 'tier = "closed"'):
            assert dead not in src, dead

    def test_the_rank_is_no_longer_read_straight_off_decision_tiers(self):
        src = self._code_only(_REPO / "scripts/telegram_command_center_send.py")
        assert 'DECISION_TIERS.get(tier) or {}).get("tier_rank")' not in src


class TestCaching:
    def test_a_config_edit_is_picked_up(self, tmp_path):
        root = _cfg(tmp_path, _MINIMAL)
        assert DT.tier_rank(root, "BUY") == 2
        _cfg(tmp_path, _MINIMAL.replace("active: {tier_rank: 2}",
                                        "active: {tier_rank: 7}"))
        assert DT.tier_rank(root, "BUY") == 7

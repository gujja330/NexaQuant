"""Self-heal must see a re-entry's close, not just the ticker's first one.

CEO 2026-10-31 · USA delivered nothing on 2026-10-30 because
canonical_lifecycle_usa.json was generated at 21:43:18 and the registry
closed ZBRA and DDOG at 21:48:55. CURRENT still carried both, the workbook
rendered them as live, and I6 refused the send.

ci_selfheal_lifecycle.py existed precisely to repair that shape of
staleness and did not fire, because its only invariant (A23) compares
TICKER strings: both names were already in exit history under their August
orphan-closed episodes, so the tickers read as "accounted for" while the
September positions sat in CURRENT.

Every test here runs against a registry and a lifecycle built inside
tmp_path. None of them read the repository's own artifacts.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

MOD = "scripts.ci_selfheal_lifecycle"


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    """The script, rooted at an empty tmp_path."""
    m = importlib.import_module(MOD)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m


def _registry(root: Path, events: list) -> None:
    p = root / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n",
                 encoding="utf-8")


def _event(oid: str, ticker: str, status: str, ts: str,
           created: str = "2026-09-30", market: str = "usa") -> dict:
    return {"opportunity_id": oid, "market": market, "runner": "R2",
            "ticker": ticker, "created_date": created, "status": status,
            "closed_date": "" if status == "ACTIVE" else "2026-10-30",
            "ts_utc": ts}


def _lifecycle(root: Path, market: str, current: list) -> None:
    p = root / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"market": market, "asof": "2026-10-31",
                             "current": current, "exits": []}),
                 encoding="utf-8")


# ── _closed_position_ids ────────────────────────────────────────────

def test_the_latest_event_decides_closed(mod, tmp_path):
    _registry(tmp_path, [
        _event("USA-R2-ZBRA-20260923-11c4b9", "ZBRA", "ACTIVE",
               "2026-09-23T17:51:21"),
        _event("USA-R2-ZBRA-20260923-11c4b9", "ZBRA", "CLOSED",
               "2026-10-30T21:48:55"),
    ])
    assert "USA-R2-ZBRA-20260923-11c4b9" in mod._closed_position_ids("usa")


def test_a_still_active_episode_is_not_closed(mod, tmp_path):
    _registry(tmp_path, [
        _event("USA-R2-AAPL-20260930-aaaaaa", "AAPL", "ACTIVE",
               "2026-09-30T19:21:06"),
    ])
    assert mod._closed_position_ids("usa") == {}


def test_the_other_market_is_not_borrowed(mod, tmp_path):
    """A market-blind lookup is its own bug class in this repo."""
    _registry(tmp_path, [
        _event("IND-R2-SBIN-20260930-bbbbbb", "SBIN", "CLOSED",
               "2026-10-30T21:48:55", market="india"),
    ])
    assert mod._closed_position_ids("usa") == {}
    assert "IND-R2-SBIN-20260930-bbbbbb" in mod._closed_position_ids("india")


# ── closed_in_current ───────────────────────────────────────────────

def test_a_closed_position_still_in_current_is_detected(mod, tmp_path):
    oid = "USA-R2-DDOG-20260930-8f3161"
    _registry(tmp_path, [_event(oid, "DDOG", "CLOSED",
                                "2026-10-30T21:48:55")])
    _lifecycle(tmp_path, "usa", [{"ticker": "DDOG", "position_id": oid}])
    assert mod.closed_in_current("usa") == [("DDOG", oid)]


def test_an_open_position_in_current_is_left_alone(mod, tmp_path):
    oid = "USA-R2-AAPL-20260930-aaaaaa"
    _registry(tmp_path, [_event(oid, "AAPL", "ACTIVE",
                                "2026-09-30T19:21:06")])
    _lifecycle(tmp_path, "usa", [{"ticker": "AAPL", "position_id": oid}])
    assert mod.closed_in_current("usa") == []


def test_a_closed_position_absent_from_current_is_fine(mod, tmp_path):
    """Closing a position is normal · only CURRENT must not show it."""
    _registry(tmp_path, [_event("USA-R2-MAA-20260915-47724c", "MAA",
                                "CLOSED", "2026-10-30T17:48:50")])
    _lifecycle(tmp_path, "usa", [])
    assert mod.closed_in_current("usa") == []


def test_the_regression_an_earlier_episode_must_not_cover_a_re_entry(
        mod, tmp_path):
    """The exact 2026-10-30 shape · this is what A23 could not see.

    ZBRA holds two episodes. The August one was orphan-closed and IS in
    exit history, so a ticker-keyed check reports the name as accounted
    for. The September re-entry closed at 21:48:55 and is the one sitting
    in CURRENT.
    """
    aug = "USA-R2-ZBRA-20260811-57e329"
    sep = "USA-R2-ZBRA-20260923-11c4b9"
    _registry(tmp_path, [
        _event(aug, "ZBRA", "ACTIVE", "2026-08-20T07:04:20", "2026-08-11"),
        _event(aug, "ZBRA", "CLOSED", "2026-08-26T17:14:32", "2026-08-11"),
        _event(sep, "ZBRA", "ACTIVE", "2026-09-23T17:51:21", "2026-09-23"),
        _event(sep, "ZBRA", "CLOSED", "2026-10-30T21:48:55", "2026-09-23"),
    ])
    _lifecycle(tmp_path, "usa", [{"ticker": "ZBRA", "position_id": sep}])

    found = mod.closed_in_current("usa")
    assert found == [("ZBRA", sep)], found

    # Both episodes are CLOSED, so the ticker is "accounted for" whichever
    # one exit history holds · a ticker-keyed check cannot tell the live
    # episode from the old one, which is exactly why A23 stayed silent.
    closed = mod._closed_position_ids("usa")
    assert {aug, sep} <= set(closed), "both episodes must read as closed"
    assert len({c.ticker for c in closed.values()}) == 1, (
        "one ticker, two episodes · the collapse that hid the re-entry")


def test_a_missing_lifecycle_is_not_a_crash(mod, tmp_path):
    _registry(tmp_path, [_event("USA-R2-X-20260930-cccccc", "X", "CLOSED",
                                "2026-10-30T21:48:55")])
    assert mod.closed_in_current("usa") == []


def test_an_unparseable_lifecycle_is_not_a_crash(mod, tmp_path):
    p = tmp_path / "reports" / "context" / "canonical_lifecycle_usa.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<<<<<<< HEAD\n{ not json", encoding="utf-8")
    _registry(tmp_path, [])
    assert mod.closed_in_current("usa") == []


def test_a_current_row_without_a_position_id_is_skipped(mod, tmp_path):
    _registry(tmp_path, [_event("USA-R2-X-20260930-cccccc", "X", "CLOSED",
                                "2026-10-30T21:48:55")])
    _lifecycle(tmp_path, "usa", [{"ticker": "X"}, "not-a-dict"])
    assert mod.closed_in_current("usa") == []


# ── heal() and main() must honour BOTH invariants ───────────────────

def test_heal_is_not_satisfied_by_a23_alone(mod, monkeypatch):
    """Regeneration leaving a closed position in CURRENT is not a repair."""
    monkeypatch.setattr(mod, "_run", lambda cmd: 0)
    monkeypatch.setattr(mod, "unaccounted", lambda m: set())
    monkeypatch.setattr(mod, "closed_in_current",
                        lambda m: [("ZBRA", "USA-R2-ZBRA-20260923-11c4b9")])
    assert mod.heal("usa", "2026-10-31") is False


def test_heal_passes_when_both_are_clean(mod, monkeypatch):
    monkeypatch.setattr(mod, "_run", lambda cmd: 0)
    monkeypatch.setattr(mod, "unaccounted", lambda m: set())
    monkeypatch.setattr(mod, "closed_in_current", lambda m: [])
    assert mod.heal("usa", "2026-10-31") is True


def test_main_fails_loudly_when_the_repair_does_not_restore(
        mod, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["x", "--market", "usa"])
    monkeypatch.setattr(mod, "unaccounted", lambda m: set())
    monkeypatch.setattr(mod, "closed_in_current",
                        lambda m: [("ZBRA", "USA-R2-ZBRA-20260923-11c4b9")])
    monkeypatch.setattr(mod, "heal", lambda m, a: False)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "::error::" in out
    assert "ZBRA" in out and "USA-R2-ZBRA-20260923-11c4b9" in out, (
        "the operator must be told WHICH position, not just which name")


def test_main_is_quiet_and_green_when_nothing_is_wrong(
        mod, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["x", "--market", "usa"])
    monkeypatch.setattr(mod, "unaccounted", lambda m: set())
    monkeypatch.setattr(mod, "closed_in_current", lambda m: [])
    called = []
    monkeypatch.setattr(mod, "heal", lambda m, a: called.append(1) or True)
    assert mod.main() == 0
    assert not called, "a clean run must not regenerate anything"
    assert "OK" in capsys.readouterr().out


def test_stale_current_alone_triggers_the_repair(mod, monkeypatch):
    """A23 clean + CURRENT stale must still regenerate · that is the bug."""
    monkeypatch.setattr(sys, "argv", ["x", "--market", "usa"])
    monkeypatch.setattr(mod, "unaccounted", lambda m: set())
    monkeypatch.setattr(mod, "closed_in_current",
                        lambda m: [("DDOG", "USA-R2-DDOG-20260930-8f3161")])
    healed = []
    monkeypatch.setattr(mod, "heal", lambda m, a: healed.append(m) or True)
    assert mod.main() == 0
    assert healed == ["usa"], "the repair never ran"

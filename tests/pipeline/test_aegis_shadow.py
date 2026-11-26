import pytest

from scripts.aegis_shadow.replay import replay
from scripts.aegis_shadow.research import profit_capture
from scripts.aegis_shadow.run import _digest, _frozen_path


def _position(pid, close, authorized_on="2026-11-25"):
    return {
        "opportunity_id": pid, "admitted": "2026-11-24",
        "bars": {"2026-11-27": {"close": close, "price_basis": "raw"}},
        "levels": {"2026-11-27": {"stop": 95, "target": 110, "price_basis": "raw",
                                  "authorized_on": authorized_on}},
    }


def test_replay_is_deterministic_and_keeps_incomplete_positions_pending():
    evidence = {
        "market": "usa", "last_committed": "2026-11-25",
        "completed_through": "2026-11-27", "sessions": ["2026-11-27"],
        "positions": [_position("target", 115), _position("stop", 90),
                      _position("future", 90, "2026-11-27"), _position("missing", None)],
    }
    report = replay(evidence)
    assert replay(evidence) == report
    assert [row["rule"] for row in report["events"]] == ["EXIT_STOP", "EXIT_TARGET"]
    assert all(row["execution_status"] == "UNKNOWN" for row in report["events"])
    assert [row["opportunity_id"] for row in report["pending"]] == ["future", "missing"]


def test_shadow_rejects_paths_outside_frozen_workspace(tmp_path):
    (tmp_path / ".aegis-local").mkdir()
    frozen = tmp_path / ".aegis-local" / "snapshot"
    frozen.mkdir()
    live = tmp_path / "live.json"
    live.write_text("{}", encoding="utf-8")
    assert _frozen_path(tmp_path, frozen) == frozen
    with pytest.raises(ValueError, match="beneath"):
        _frozen_path(tmp_path, live)
    with pytest.raises(ValueError, match="escapes"):
        _digest(frozen, "../../live.json")


def test_profit_capture_uses_frozen_highs_and_excludes_open_episodes():
    closed = {
        "opportunity_id": "closed", "mode": "SIMULATED", "side": "LONG",
        "entry_date": "2026-11-23", "entry_price": 100,
        "exit_date": "2026-11-24", "exit_price": 120, "price_basis": "raw",
        "exit_observation": "SESSION_CLOSE",
        "sessions": ["2026-11-24"],
        "highs": {"2026-11-24": {"high": 140, "price_basis": "raw"},
                  "2026-11-25": {"high": 200, "price_basis": "raw"}},
    }
    open_episode = dict(closed, opportunity_id="open", exit_date=None)
    report = profit_capture({"asof": "2026-11-26", "episodes": [closed, open_episode]})
    assert report["excluded_ids"] == ["open"]
    assert report["episodes"][0]["peak_profit_capture_pct"] == pytest.approx(50)

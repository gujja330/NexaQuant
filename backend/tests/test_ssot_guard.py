"""Sprint K Part 28 follow-up · SSoT Strong Guard tests.

Covers the failure modes that motivated the guard:
  · SSoT ImportError (2026-08-11)
  · CI cascade → SSoT input starvation (2026-08-12)
  · 3 consecutive failures with no fallback (2026-08-13)
  · Guard self-bug where fallback destructively overwrote fresh data (2026-08-14)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.ssot.guard import (   # noqa: E402
    SSoTHealth, _preflight, _postflight, _invoke_ssot,
    _try_fallback_to_previous_day,
)


def test_preflight_reports_missing_v3(tmp_path: Path):
    """Missing recommendations_v3.json is a fatal pre-flight failure."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "usa" / "reports").mkdir(parents=True)
    ok, checks = _preflight(tmp_path, "india", "2026-08-14")
    assert not ok
    assert checks["recommendations_v3.json_exists"] is False


def test_preflight_detects_stale_aegis_today(tmp_path: Path):
    """India · aegis_today.csv older than 3 days = STALE."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "data").mkdir()
    # Fresh v3 (so that check passes)
    (tmp_path / "reports" / "recommendations_v3.json").write_text("{}")
    # Stale aegis_today.csv (Generated=2026-07-01 for asof=2026-08-14 = 44 days stale)
    (tmp_path / "data" / "aegis_today.csv").write_text(
        "Generated,Profile,Stock\n2026-07-01,X,Y\n"
    )
    ok, checks = _preflight(tmp_path, "india", "2026-08-14")
    assert not ok
    assert checks.get("aegis_today.csv_STALE") is True
    assert checks.get("aegis_today.csv_age_days") == 44


def test_preflight_passes_when_all_inputs_fresh(tmp_path: Path):
    """Everything present + fresh · pre-flight OK."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "reports" / "recommendations_v3.json").write_text("{}")
    (tmp_path / "data" / "aegis_today.csv").write_text(
        "Generated,Profile\n2026-08-14,X\n"
    )
    ok, checks = _preflight(tmp_path, "india", "2026-08-14")
    assert ok
    assert checks["backend.research_importable"] is True


def test_postflight_rejects_missing_output(tmp_path: Path):
    (tmp_path / "reports").mkdir()
    ok, checks = _postflight(tmp_path, "india", "2026-08-14")
    assert not ok
    assert checks["recommendations.json_exists"] is False


def test_postflight_rejects_asof_mismatch(tmp_path: Path):
    """Output for wrong date = fail."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "recommendations.json").write_text(
        json.dumps({"asof": "2026-08-11", "recommendations": [{"ticker": "X"}]})
    )
    ok, checks = _postflight(tmp_path, "india", "2026-08-14")
    assert not ok
    assert "asof_mismatch" in checks


def test_postflight_rejects_empty_recommendations(tmp_path: Path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "recommendations.json").write_text(
        json.dumps({"asof": "2026-08-14", "recommendations": []})
    )
    ok, checks = _postflight(tmp_path, "india", "2026-08-14")
    assert not ok
    assert checks.get("empty_recommendations") is True


def test_postflight_accepts_healthy_output(tmp_path: Path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "recommendations.json").write_text(
        json.dumps({
            "asof": "2026-08-14",
            "universe_role": "selected_candidates",
            "recommendations": [{"ticker": "X"}, {"ticker": "Y"}],
        })
    )
    ok, checks = _postflight(tmp_path, "india", "2026-08-14")
    assert ok
    assert checks["n_recs"] == 2
    assert checks["universe_role"] == "selected_candidates"


def test_invoke_ssot_treats_refused_snapshot_as_success(tmp_path: Path):
    """Guard self-bug regression · SSoT returning non-zero because today's
    snapshot ALREADY exists is not a failure. The data IS fresh."""
    fake_stdout = (
        "[recommendation_ssot:india] REFUSED · snapshot for 2026-08-14 "
        "already exists at reports/recommendations_history/india/2026-08-14.json.\n"
        "  · Use 'scripts/stamp_only.py' for display or canonical stamp updates."
    )
    fake_result = MagicMock(returncode=1, stdout=fake_stdout, stderr="")
    with patch("subprocess.run", return_value=fake_result):
        ok, msg = _invoke_ssot(tmp_path, "india", "2026-08-14", force=False)
    assert ok is True
    assert "refused_idempotent" in msg


def test_invoke_ssot_treats_real_failure_as_failure(tmp_path: Path):
    fake_result = MagicMock(returncode=1, stdout="",
                                    stderr="Traceback (most recent call last):\nImportError: xyz")
    with patch("subprocess.run", return_value=fake_result):
        ok, msg = _invoke_ssot(tmp_path, "india", "2026-08-14", force=False)
    assert ok is False
    assert "ImportError" in msg


def test_fallback_reads_most_recent_previous_snapshot(tmp_path: Path):
    (tmp_path / "reports" / "recommendations_history" / "india").mkdir(parents=True)
    hist = tmp_path / "reports" / "recommendations_history" / "india"
    (hist / "2026-07-15.json").write_text(json.dumps({"asof": "2026-07-15", "recommendations": [{"ticker": "OLD"}]}))
    (hist / "2026-08-05.json").write_text(json.dumps({"asof": "2026-08-05", "recommendations": [{"ticker": "NEW"}]}))
    ok, info = _try_fallback_to_previous_day(tmp_path, "india", "2026-08-14")
    assert ok
    assert info == "2026-08-05"
    out = json.loads((tmp_path / "reports" / "recommendations.json").read_text(encoding="utf-8"))
    assert out["degraded_from_previous_day"] is True
    assert out["fallback_source_date"] == "2026-08-05"
    assert out["recommendations"][0]["ticker"] == "NEW"


def test_fallback_returns_false_when_no_history(tmp_path: Path):
    (tmp_path / "reports").mkdir()
    ok, info = _try_fallback_to_previous_day(tmp_path, "india", "2026-08-14")
    assert not ok
    assert "no history" in info.lower()

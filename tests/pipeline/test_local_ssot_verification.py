import json

from backend.recommendation.ssot.guard import verify_published


def test_local_verification_reuses_only_the_sealed_recommendations(tmp_path):
    asof = "2026-11-24"
    reports = tmp_path / "reports"
    (reports / "context").mkdir(parents=True)
    (reports / "recommendations_history/india").mkdir(parents=True)
    payload = {"asof": asof, "recommendations": [{"ticker": "XYZ"}]}
    latest = reports / "recommendations.json"
    latest.write_text(json.dumps(payload))
    archive = reports / "recommendations_history/india" / f"{asof}.json"
    archive.write_text(json.dumps({**payload, "snapshot_asof": asof}))
    health = reports / "context/ssot_health.json"
    health.write_text(json.dumps({"india": {"verdict": "GREEN", "output_asof": asof}}))
    before = archive.read_bytes()

    assert verify_published(tmp_path, "india", asof)[0]
    assert verify_published(tmp_path, "india", asof)[0]
    assert archive.read_bytes() == before

    latest.write_text(json.dumps({**payload, "recommendations": [{"ticker": "ABC"}]}))
    assert not verify_published(tmp_path, "india", asof)[0]
    latest.write_text(json.dumps(payload))
    health.write_text(json.dumps({"india": {"verdict": "YELLOW", "output_asof": asof}}))
    assert not verify_published(tmp_path, "india", asof)[0]


def test_current_india_ssot_must_match_verified_price_session(tmp_path, monkeypatch):
    from backend.recommendation.ssot import price_session

    asof = "2026-11-25"
    monkeypatch.setattr(price_session, "expected_session", lambda *args: asof)
    reports = tmp_path / "reports"
    (reports / "context").mkdir(parents=True)
    history = reports / "recommendations_history/india"
    history.mkdir(parents=True)
    (reports / "context/ssot_health.json").write_text(json.dumps({
        "india": {"verdict": "GREEN", "output_asof": asof},
    }))
    payload = {"asof": asof, "recommendations": [{"ticker": "ABC"}], "price_session": "2026-11-23"}
    latest = reports / "recommendations.json"
    archive = history / f"{asof}.json"
    latest.write_text(json.dumps(payload))
    archive.write_text(json.dumps({**payload, "snapshot_asof": asof}))
    assert not verify_published(tmp_path, "india", asof)[0]
    payload["price_session"] = asof
    latest.write_text(json.dumps(payload))
    archive.write_text(json.dumps({**payload, "snapshot_asof": asof}))
    assert verify_published(tmp_path, "india", asof)[0]

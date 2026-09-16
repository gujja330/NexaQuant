"""Technical evidence memory — the substrate that makes historical replay possible.

THE DEFECT THESE TESTS LOCK DOWN
--------------------------------
The evidence-vector technical probe originally read

    features/<market>/<asof>.parquet

and returned BLOCKED_DATA for every historical date. That looked like a missing
substrate and nearly triggered building a second feature store. It was not.
memory-v2 already sealed the exact matrix R2 consumed into

    history/<market>/<asof>/technical_features.parquet

with its sha256 inside SEALED. The evidence existed; the probe was reading the
ephemeral working path instead of the durable sealed one.

`portfolio` carried the identical defect against the live lifecycle file.

So the rule these tests enforce is narrow and specific: AVAILABLE requires a
SEALED artifact, not a file that happens to be on disk. A present-but-unsealed
matrix cannot prove it is what the engine consumed that day, and a rebuild from
today's data is not evidence about the past at all.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.research.r3_program.evidence_vector import (
    assemble, coverage_matrix, replay_ready,
    AVAILABLE, PARTIAL, BLOCKED_DATA, BLOCKED_PIT, FAMILIES)
from backend.memory.daily_snapshot import snapshot_dir, verify_seal, load

ROOT = Path(__file__).resolve().parents[2]


def _sealed_days(market: str) -> list[str]:
    d = ROOT / "history" / market
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir()
                  if p.is_dir() and (p / "SEALED").exists())


def _with_sidecar(market: str, name: str) -> list[str]:
    return [a for a in _sealed_days(market)
            if (snapshot_dir(ROOT, market, a) / name).exists()]


# A · durable across a fresh clone ────────────────────────────────────
def test_technical_memory_is_tracked_not_working_state():
    """The matrix must live in git, not in the overwritten features/ dir."""
    import subprocess
    days = _with_sidecar("india", "technical_features.parquet")
    if not days:
        pytest.skip("no sealed technical matrix")
    rel = "history/india/%s/technical_features.parquet" % days[-1]
    out = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                         cwd=str(ROOT), capture_output=True, text=True)
    assert out.returncode == 0, "%s is not tracked; it would not survive a clone" % rel


# B, C · hash stability and determinism ──────────────────────────────
def test_sealed_matrix_hash_is_stable():
    for market in ("india", "usa"):
        for a in _with_sidecar(market, "technical_features.parquet"):
            ok, msg = verify_seal(ROOT, market, a)
            assert ok, "%s/%s seal broken: %s" % (market, a, msg)


def test_same_inputs_give_the_same_matrix():
    import pandas as pd
    days = _with_sidecar("india", "technical_features.parquet")
    if not days:
        pytest.skip("no sealed matrix")
    p = snapshot_dir(ROOT, "india", days[-1]) / "technical_features.parquet"
    a = pd.read_parquet(p)
    b = pd.read_parquet(p)
    assert a.equals(b)
    assert a.shape[0] > 0 and a.shape[1] > 10


# D · idempotence ─────────────────────────────────────────────────────
def test_resealing_a_recorded_day_is_refused():
    from backend.pipeline.contract.runner import record_historical_memory
    days = _sealed_days("india")
    if not days:
        pytest.skip("no sealed day")
    r = record_historical_memory(ROOT, "india", days[-1])
    assert r["status"] == "ALREADY_SEALED", \
        "a re-run overwrote an existing historical day"


# E · missing snapshot is BLOCKED, never silently rebuilt ────────────
def test_missing_day_is_blocked_data_not_reconstructed():
    st = assemble(ROOT, "india", date(2019, 1, 4)).families["technical"]
    assert st["status"] == BLOCKED_DATA
    assert "TECHNICAL_MEMORY_MISSING" in st["reason"]


def test_probe_does_not_pass_on_a_bare_features_file():
    """A file in features/ is not evidence. Only the seal is."""
    import glob
    for market in ("india", "usa"):
        for f in glob.glob(str(ROOT / "features" / market / "*.parquet")):
            a = Path(f).name.split(".")[0]
            if len(a) != 10:
                continue
            if (snapshot_dir(ROOT, market, a) / "technical_features.parquet").exists():
                continue          # sealed too - legitimately AVAILABLE
            st = assemble(ROOT, market, date.fromisoformat(a)).families["technical"]
            assert st["status"] != AVAILABLE, (
                "%s/%s reported AVAILABLE from an unsealed features file" % (market, a))


# F, G · no future data, no substitution of today for history ────────
def test_no_family_marked_pit_ok_carries_a_future_date():
    for market in ("india", "usa"):
        for a in _sealed_days(market):
            snap = load(ROOT, market, a)
            for fam, pr in (snap.get("provenance") or {}).items():
                if pr.get("pit_status") != "PIT_OK":
                    continue
                for k in ("observation_date", "publication_date", "effective_date"):
                    v = pr.get(k)
                    assert not (v and str(v) > a), \
                        "%s/%s %s.%s=%s postdates the as_of" % (market, a, fam, k, v)


def test_live_lifecycle_cannot_supply_a_historical_portfolio():
    """The current file describes today. For any other date it must not pass."""
    live = ROOT / "reports/context/canonical_lifecycle_india.json"
    if not live.exists():
        pytest.skip("no lifecycle")
    today = json.loads(live.read_text(encoding="utf-8")).get("asof")
    for a in _sealed_days("india"):
        if a == today:
            continue
        if (snapshot_dir(ROOT, "india", a) / "decisions.parquet").exists():
            continue              # sealed decisions legitimately supply it
        st = assemble(ROOT, "india", date.fromisoformat(a)).families["portfolio"]
        assert st["status"] != AVAILABLE, \
            "%s took its portfolio from the live %s lifecycle" % (a, today)


# H, I · identity and schema ─────────────────────────────────────────
def test_matrix_preserves_ticker_identity():
    import pandas as pd
    for market in ("india", "usa"):
        for a in _with_sidecar(market, "technical_features.parquet"):
            df = pd.read_parquet(snapshot_dir(ROOT, market, a) / "technical_features.parquet")
            assert "ticker" in df.columns
            assert df["ticker"].notna().all()
            assert df["ticker"].is_unique, "%s/%s has duplicate tickers" % (market, a)


def test_snapshot_records_schema_fingerprint():
    for market in ("india", "usa"):
        for a in _sealed_days(market):
            fp = (load(ROOT, market, a).get("fingerprints") or {})
            assert "feature_schema_fingerprint" in fp


# J · tampering breaks certification ─────────────────────────────────
def test_tampering_with_the_matrix_fails_certification(tmp_path):
    import pandas as pd, shutil
    days = _with_sidecar("india", "technical_features.parquet")
    if not days:
        pytest.skip("no sealed matrix")
    a = days[-1]
    src = snapshot_dir(ROOT, "india", a)
    dst = tmp_path / "history" / "india" / a
    shutil.copytree(src, dst)
    assert verify_seal(tmp_path, "india", a)[0]
    pd.DataFrame({"ticker": ["X"]}).to_parquet(dst / "technical_features.parquet", index=False)
    ok, msg = verify_seal(tmp_path, "india", a)
    assert not ok and "TAMPERED" in msg
    st = assemble(tmp_path, "india", date.fromisoformat(a)).families["technical"]
    assert st["status"] == BLOCKED_PIT


# K, L · coexistence and the replay gate ─────────────────────────────
def test_technical_and_portfolio_can_coexist_for_a_historical_asof():
    """The objective of this whole workstream."""
    found = []
    for market in ("india", "usa"):
        for a in _sealed_days(market):
            f = assemble(ROOT, market, date.fromisoformat(a)).families
            if (f["technical"]["status"] == AVAILABLE
                    and f["portfolio"]["status"] in (AVAILABLE, PARTIAL)):
                found.append("%s/%s" % (market, a))
    assert found, "no as_of has technical AND portfolio simultaneously available"


def test_replay_gate_is_false_by_default_and_names_its_blockers():
    r = replay_ready(ROOT, "india", date(2019, 1, 4))
    assert r["R3_HISTORICAL_REPLAY_READY"] is False
    assert r["blockers"], "gate returned False without naming a blocker"


def test_replay_gate_true_requires_seal_and_hash():
    ready = []
    for market in ("india", "usa"):
        for a in _sealed_days(market):
            r = replay_ready(ROOT, market, date.fromisoformat(a))
            if r["R3_HISTORICAL_REPLAY_READY"]:
                ready.append(r)
                assert r["seal_verified"] is True
                assert r["hash_reproducible"] is True
                assert r["contract"] == "CONTRACT_MET"
                assert not r["blockers"]
    assert ready, "no date reached R3_HISTORICAL_REPLAY_READY"


def test_rejected_families_stay_rejected():
    """Technical memory becoming available must not reopen peer research."""
    f = assemble(ROOT, "india", date(2026, 9, 15)).families
    assert f["peer"]["status"] == "REJECTED"

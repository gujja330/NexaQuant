"""Sprint 2.5 regression suite — Feature Store framework + AI agents.

All tests exercise the walk-forward code paths: registry stability,
builder determinism, snapshot persistence, cutoff filtering, and the
no-recommendation contract for the four Feature Store AI agents.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.canonical.model              import INDIA_PROFILE, USA_PROFILE               # noqa: E402
from backend.feature_store                 import (                                          # noqa: E402
    FEATURE_REGISTRY, list_categories, FeatureBuilder,
    schema_fingerprint, snapshot_path, read_snapshot, build_and_persist,
)
from backend.feature_store.feature_registry import FeatureCategory                          # noqa: E402
from backend.feature_store.feature_versioning import SCHEMA_VERSION                          # noqa: E402
from backend.feature_store.feature_validation import validate_snapshot                       # noqa: E402
from backend.ai import (                                                                      # noqa: E402
    feature_anomaly, feature_quality, feature_importance, feature_conflict,
)


# ── Registry + versioning ─────────────────────────────────────
def test_registry_has_all_10_categories():
    cats = {c.value for c in list_categories()}
    expected = {c.value for c in FeatureCategory}
    missing = expected - cats
    assert not missing, f"registry missing categories: {missing}"
    print(f"  [OK] registry has all 10 categories: {len(cats)} present")


def test_registry_no_duplicate_names():
    names = [f.name for f in FEATURE_REGISTRY]
    assert len(names) == len(set(names)), "registry has duplicate feature names"
    print(f"  [OK] registry has {len(names)} unique features")


def test_schema_fingerprint_stable():
    fp1 = schema_fingerprint()
    fp2 = schema_fingerprint()
    assert fp1 == fp2 and len(fp1) == 12
    assert SCHEMA_VERSION
    print(f"  [OK] schema fingerprint stable: {fp1} · version {SCHEMA_VERSION}")


# ── Builder ────────────────────────────────────────────────────
def test_builder_produces_dataframe_with_all_registry_cols():
    b = FeatureBuilder(_ROOT, USA_PROFILE)
    df = b.build(asof=date.today())
    assert df is not None and not df.empty
    registered = [f.name for f in FEATURE_REGISTRY]
    missing = set(registered) - set(df.columns)
    assert not missing, f"builder output missing registered columns: {missing}"
    print(f"  [OK] builder returns DataFrame with {len(df)} rows × {len(df.columns)} cols "
           f"(matches registry)")


def test_builder_deterministic():
    """Same repo state + same cutoff → identical DataFrame."""
    b = FeatureBuilder(_ROOT, USA_PROFILE)
    df1 = b.build(asof=date.today())
    df2 = b.build(asof=date.today())
    # Restrict to numeric columns for a robust equality check
    num_cols = [c for c in df1.columns if pd.api.types.is_numeric_dtype(df1[c])]
    assert (df1[num_cols].fillna(-999).values == df2[num_cols].fillna(-999).values).all(), \
        "builder produced non-deterministic output"
    print(f"  [OK] builder deterministic across {len(num_cols)} numeric columns")


def test_walk_forward_cutoff_drops_future_rows():
    """A past cutoff yields fewer or equal rows than today."""
    b = FeatureBuilder(_ROOT, USA_PROFILE)
    df_now = b.build(asof=date.today())
    df_past = b.build(asof=date(2020, 1, 1))
    # Past cutoff: bar rows within cutoff may be empty → many nulls (that's fine)
    assert len(df_past) <= len(df_now), "past cutoff produced MORE rows than today"
    print(f"  [OK] walk-forward cutoff filter: now={len(df_now)} past={len(df_past)}")


# ── Validation ─────────────────────────────────────────────────
def test_validate_snapshot_produces_verdict():
    df = pd.DataFrame({
        "market":   ["usa"] * 10, "ticker": [f"T{i}" for i in range(10)],
        "asof":     ["2026-07-20"] * 10, "sector": ["Tech"] * 10, "currency": ["USD"] * 10,
        "close":    list(range(10)), "rsi_14": [50.0] * 10,
    })
    r = validate_snapshot(df, FEATURE_REGISTRY)
    assert r.verdict in {"PASS", "WARNING", "FAIL"}
    assert r.n_rows == 10
    print(f"  [OK] validation returns verdict={r.verdict} · n_features={r.n_features}")


# ── Persistence ─────────────────────────────────────────────────
def test_build_and_persist_writes_parquet_and_manifest():
    summary = build_and_persist(_ROOT, USA_PROFILE, asof=date.today())
    assert summary["n_rows"] > 0
    assert summary["schema_fingerprint"] == schema_fingerprint()
    p = snapshot_path(_ROOT, "usa", date.today())
    # The exact filename may be `.rebuilt_HHMMSS.parquet` on a re-emit — check either
    parent = p.parent
    assert parent.exists() and any(parent.glob(f"{date.today().isoformat()}*.parquet")), \
        f"no snapshot parquet emitted under {parent}"
    manifest = _ROOT / "features" / "manifest.jsonl"
    assert manifest.exists()
    print(f"  [OK] build_and_persist wrote snapshot + manifest ({summary['n_rows']} rows)")


# ── AI agents ──────────────────────────────────────────────────
def test_feature_ai_agents_run():
    df = read_snapshot(_ROOT, "usa", date.today())
    assert df is not None and not df.empty
    val = validate_snapshot(df, FEATURE_REGISTRY)
    for name, out in [
        ("anomaly",    feature_anomaly.run(df, "usa")),
        ("quality",    feature_quality.run(val, "usa")),
        ("importance", feature_importance.run(df, "usa")),
        ("conflict",   feature_conflict.run(df, "usa")),
    ]:
        assert out.agent
        assert out.headline
        assert out.narrative
    print(f"  [OK] all 4 feature AI agents run and produce narratives")


def test_feature_ai_agents_no_recommendation_output():
    df = read_snapshot(_ROOT, "usa", date.today())
    val = validate_snapshot(df, FEATURE_REGISTRY)
    outs = [feature_anomaly.run(df, "usa"), feature_quality.run(val, "usa"),
             feature_importance.run(df, "usa"), feature_conflict.run(df, "usa")]
    forbidden = {"buy", "sell", "target_price", "recommendation", "action"}
    for o in outs:
        for f in o.findings:
            keys = set(f.keys()) if isinstance(f, dict) else set()
            leak = keys & forbidden
            assert not leak, f"{o.agent} findings leaked recommendation key: {leak}"
    print(f"  [OK] all 4 feature AI agents obey no-recommendation contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_feature_store_runner_emits_valid_json():
    r = subprocess.run(
        [sys.executable, "india/feature_store/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    summary = json.loads((_ROOT / "reports" / "feature_store_summary.json")
                            .read_text(encoding="utf-8"))
    assert summary["market"] == "india"
    assert "verdict" in summary and "n_rows" in summary
    print(f"  [OK] india feature store runner: verdict={summary['verdict']} "
           f"rows={summary['n_rows']} features={summary['n_features']}")


def test_usa_feature_store_runner_emits_valid_json():
    r = subprocess.run(
        [sys.executable, "usa/research/feature_store/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    summary = json.loads((_ROOT / "usa" / "reports" / "feature_store_summary.json")
                            .read_text(encoding="utf-8"))
    assert summary["market"] == "usa"
    print(f"  [OK] usa feature store runner: verdict={summary['verdict']} "
           f"rows={summary['n_rows']} features={summary['n_features']}")


TESTS = [
    test_registry_has_all_10_categories,
    test_registry_no_duplicate_names,
    test_schema_fingerprint_stable,
    test_builder_produces_dataframe_with_all_registry_cols,
    test_builder_deterministic,
    test_walk_forward_cutoff_drops_future_rows,
    test_validate_snapshot_produces_verdict,
    test_build_and_persist_writes_parquet_and_manifest,
    test_feature_ai_agents_run,
    test_feature_ai_agents_no_recommendation_output,
    test_india_feature_store_runner_emits_valid_json,
    test_usa_feature_store_runner_emits_valid_json,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 2.5 · Feature Store + 4 AI agents · Regression Tests")
    print("=" * 70)
    n_pass = 0; n_fail = 0
    for t in TESTS:
        try:
            t(); n_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}"); n_fail += 1
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}"); n_fail += 1
    print()
    print(f"  {n_pass} passed, {n_fail} failed of {len(TESTS)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

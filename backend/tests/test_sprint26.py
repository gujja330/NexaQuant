"""Sprint 2.6 regression — Feature Intelligence + Model Registry + Promotion Gate + AI Research Agent."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.feature_store.feature_registry import (                                        # noqa: E402
    FEATURE_REGISTRY, FeatureStatus, Feature, FeatureCategory, active_feature_names,
)
from backend.feature_intelligence          import (                                           # noqa: E402
    validate_governance, persist_quality_snapshot,
    detect_drift, psi, js_divergence, ks_statistic,
    compute_importance, select_features,
    propose_candidate, evaluate_candidate,
)
from backend.model_registry.registry       import (                                          # noqa: E402
    register_model, get_model, list_models, stamp, ModelStatus,
)
from backend.promotion.promotion_gate      import (                                          # noqa: E402
    check_promotion, approve_feature, PromotionCriteria,
)
from backend.ai import feature_research                                                       # noqa: E402


# ── Governance ──────────────────────────────────────────────────
def test_governance_returns_verdict():
    r = validate_governance(date.today())
    assert r.verdict in {"PASS", "WARNING", "FAIL"}
    assert r.n_features == len(FEATURE_REGISTRY)
    print(f"  [OK] governance verdict={r.verdict}  rationale_cov={r.coverage_rationale_pct:.1f}%")


def test_governance_flags_missing_rationale():
    r = validate_governance(date.today())
    # 81 registered features, only 5 are identity-exempt.
    # If NONE have rationale filled, we expect missing count = 76
    assert len(r.missing_rationale) > 0, "governance should flag features lacking rationale"
    print(f"  [OK] governance flags {len(r.missing_rationale)} features missing rationale")


def test_feature_status_field_exists():
    """Every feature has a status field (Sprint 2.6 schema extension)."""
    for f in FEATURE_REGISTRY:
        assert hasattr(f, "status")
        assert f.status in {FeatureStatus.ACTIVE, FeatureStatus.EXPERIMENTAL, FeatureStatus.DEPRECATED}
    print(f"  [OK] all {len(FEATURE_REGISTRY)} features carry a status field")


# ── Drift ───────────────────────────────────────────────────────
def test_drift_metrics_return_values_on_synthetic_data():
    a = pd.Series(np.linspace(0, 1, 100))
    b = pd.Series(np.linspace(0.05, 1.05, 100))    # shifted
    p = psi(a, b); j = js_divergence(a, b); k = ks_statistic(a, b)
    assert p is not None and p >= 0
    assert j is not None and j >= 0
    assert k is not None and 0 <= k <= 1
    print(f"  [OK] drift metrics on synthetic: psi={p:.4f} js={j:.4f} ks={k:.4f}")


def test_drift_no_reference_case():
    df_now = pd.DataFrame({"market": ["usa"] * 10, "close": range(10)})
    r = detect_drift(df_now, None, date.today(), None)
    assert r.verdict == "NO_REFERENCE"
    print(f"  [OK] drift NO_REFERENCE when no prior snapshot")


# ── Importance ──────────────────────────────────────────────────
def test_importance_runs_label_free():
    df = pd.DataFrame({
        "market":  ["usa"] * 20, "ticker": [f"T{i}" for i in range(20)],
        "asof": ["2026-07-20"] * 20, "sector": ["Tech"] * 20, "currency": ["USD"] * 20,
        "colA":    np.linspace(0, 10, 20),
        "colB":    np.linspace(0, 10, 20) + np.random.default_rng(42).normal(0, 0.3, 20),
    })
    r = compute_importance(df, target=None)
    assert r.n_features_scored == 2
    assert r.with_labels is False
    print(f"  [OK] label-free importance: {r.n_features_scored} scored, methods={r.method_available}")


def test_importance_with_target_adds_supervised_metrics():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "market": ["usa"] * 50, "ticker": [f"T{i}" for i in range(50)],
        "asof": ["2026-07-20"] * 50, "sector": ["X"] * 50, "currency": ["USD"] * 50,
        "colA":  rng.normal(size=50),
    })
    target = df["colA"] * 2 + rng.normal(0, 0.1, 50)   # strong signal
    r = compute_importance(df, target=target)
    assert r.with_labels is True
    row = r.per_feature[0]
    assert row["pearson"] is not None and abs(row["pearson"]) > 0.9
    assert row["spearman"] is not None
    print(f"  [OK] supervised importance detected pearson={row['pearson']:.3f}")


# ── Selection ───────────────────────────────────────────────────
def test_selection_removes_constants_and_duplicates():
    df = pd.DataFrame({
        "market": ["usa"] * 30, "ticker": [f"T{i}" for i in range(30)],
        "asof": ["2026-07-20"] * 30, "sector": ["X"] * 30, "currency": ["USD"] * 30,
        "const": [5.0] * 30,
        "colA":  np.linspace(0, 10, 30),
        "colA_dup": np.linspace(0, 10, 30) + 1e-10,   # identical
    })
    r = select_features(df, importance_result=None, target=None)
    assert "const" in r.removed_constants
    kept = set(r.selected)
    assert len(kept & {"colA", "colA_dup"}) <= 1   # only one survives
    print(f"  [OK] selection removed constants ({len(r.removed_constants)}) + duplicates "
           f"({len(r.removed_duplicates)}); kept {r.n_selected}/{r.n_input}")


# ── Evolution ───────────────────────────────────────────────────
def test_evolution_candidate_lifecycle():
    c = propose_candidate(
        name="test_candidate", category=FeatureCategory.TECHNICAL,
        formula="(a + b) / c",
        business_rationale="testing",
        economic_intuition="testing",
        proposed_by="test",
    )
    assert c.name == "test_candidate"
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    target = values * 0.8
    ev = evaluate_candidate(c, values, target)
    assert ev.verdict in {"READY_FOR_BACKTEST", "NEEDS_METADATA", "REJECT"}
    print(f"  [OK] candidate evaluation verdict={ev.verdict}")


# ── Model Registry ──────────────────────────────────────────────
def test_model_registry_registers_and_retrieves():
    rec = register_model(_ROOT,
        model_id="test.model.v1", engine="recommendation", market="usa", version="1.0.0",
        feature_set_version="fs-abc123", schema_version="fs-abc123",
        approval_status=ModelStatus.EXPERIMENTAL, notes="regression test")
    assert rec.model_id == "test.model.v1"
    got = get_model(_ROOT, "test.model.v1")
    assert got is not None and got.engine == "recommendation"
    st = stamp(_ROOT, "test.model.v1")
    assert st["model_id"] == "test.model.v1"
    print(f"  [OK] model registry: register + get + stamp round-trip")


def test_unregistered_stamp_warns():
    st = stamp(_ROOT, "nonexistent.model")
    assert st.get("status") == "UNREGISTERED"
    print(f"  [OK] stamp warns on unregistered model")


# ── Promotion Gate ──────────────────────────────────────────────
def test_promotion_gate_blocks_without_evidence():
    d = check_promotion("feature", "test_feature", evidence={"business_rationale": "why"})
    # Missing walk-forward evidence → BLOCKED
    assert d.verdict == "BLOCKED"
    assert len(d.reasons) > 0
    print(f"  [OK] promotion gate BLOCKED without WF/backtest evidence")


def test_promotion_gate_allows_with_full_evidence():
    evidence = {
        "business_rationale": "why",
        "economic_intuition": "how",
        "formula": "x + y",
        "walk_forward": {"n_windows": 5, "p_value": 0.01, "stability_score": 0.75},
        "backtest": {"passed": True},
    }
    d = check_promotion("feature", "test_feature", evidence=evidence)
    assert d.verdict == "READY_FOR_APPROVAL", f"expected READY_FOR_APPROVAL, got {d.verdict}: {d.reasons}"
    print(f"  [OK] promotion gate READY_FOR_APPROVAL with complete evidence")


def test_approve_feature_requires_ready_verdict():
    """Cannot approve a BLOCKED candidate."""
    d_blocked = check_promotion("feature", "blocked_feat", evidence={})
    try:
        approve_feature(_ROOT, "blocked_feat", "test-operator", d_blocked)
        assert False, "expected ValueError"
    except ValueError:
        pass
    print(f"  [OK] approve_feature rejects BLOCKED decisions")


# ── AI Research Agent ───────────────────────────────────────────
def test_research_agent_generates_hypotheses():
    gov = validate_governance(date.today())
    df = pd.DataFrame({
        "market": ["usa"] * 30, "ticker": [f"T{i}" for i in range(30)],
        "macro_vix": [20.0] * 30, "macro_move": [90.0] * 30,
        "macro_dxy": [28.0] * 30, "macro_wti_oil": [80.0] * 30,
    })
    imp = compute_importance(df, target=None)
    out = feature_research.run(df, gov, imp, "usa", date.today(), top_k=3)
    assert out.agent == "feature_research"
    assert out.headline and out.narrative
    hypotheses = [f for f in out.findings if f.get("type") == "hypothesis"]
    assert len(hypotheses) == 3
    for h in hypotheses:
        assert h.get("business_rationale") and h.get("economic_intuition"), \
            "every hypothesis must have business rationale + economic intuition"
    print(f"  [OK] research agent proposed {len(hypotheses)} governed hypotheses")


def test_research_agent_never_promotes():
    """Contract: research agent findings never include buy/sell/approve/promote."""
    gov = validate_governance(date.today())
    df = pd.DataFrame({"market": ["usa"] * 10, "ticker": ["T"] * 10})
    imp = compute_importance(df, target=None)
    out = feature_research.run(df, gov, imp, "usa", date.today())
    forbidden = {"buy", "sell", "target_price", "recommendation", "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"research agent leaked: {leak}"
    print(f"  [OK] research agent obeys no-promotion contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_feature_intel_runner():
    r = subprocess.run(
        [sys.executable, "india/feature_intelligence/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    summary = json.loads((_ROOT / "reports" / "feature_intelligence_summary.json")
                            .read_text(encoding="utf-8"))
    assert summary["market"] == "india"
    print(f"  [OK] india feature intel: gov={summary['governance_verdict']} "
           f"drift={summary['drift_verdict']} sel={summary['n_selected']}/{summary['n_input']}")


def test_usa_feature_intel_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/feature_intelligence/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    summary = json.loads((_ROOT / "usa" / "reports" / "feature_intelligence_summary.json")
                            .read_text(encoding="utf-8"))
    assert summary["market"] == "usa"
    print(f"  [OK] usa feature intel: gov={summary['governance_verdict']} "
           f"drift={summary['drift_verdict']} sel={summary['n_selected']}/{summary['n_input']}")


TESTS = [
    test_governance_returns_verdict,
    test_governance_flags_missing_rationale,
    test_feature_status_field_exists,
    test_drift_metrics_return_values_on_synthetic_data,
    test_drift_no_reference_case,
    test_importance_runs_label_free,
    test_importance_with_target_adds_supervised_metrics,
    test_selection_removes_constants_and_duplicates,
    test_evolution_candidate_lifecycle,
    test_model_registry_registers_and_retrieves,
    test_unregistered_stamp_warns,
    test_promotion_gate_blocks_without_evidence,
    test_promotion_gate_allows_with_full_evidence,
    test_approve_feature_requires_ready_verdict,
    test_research_agent_generates_hypotheses,
    test_research_agent_never_promotes,
    test_india_feature_intel_runner,
    test_usa_feature_intel_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 2.6 · Feature Intelligence + Model Registry + Promotion + AI Research")
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

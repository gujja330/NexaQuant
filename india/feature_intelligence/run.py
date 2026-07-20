"""AEGIS India · Feature Intelligence runner (Sprint 2.6).

Runs governance + quality + drift + importance + selection + AI research
against the most recent Feature Store snapshot. Emits:
  reports/feature_intelligence.json          (full engine output)
  reports/feature_intelligence_summary.json  (compact for dashboard)
  reports/ai_feature_research.json           (research agent narrative)
  reports/selected_features.json             (the ACTIVE feature subset
                                               downstream engines consume)
"""
from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.canonical.model              import INDIA_PROFILE                             # noqa: E402
from backend.feature_store                 import FEATURE_REGISTRY, schema_fingerprint     # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.feature_intelligence          import (                                          # noqa: E402
    validate_governance, persist_quality_snapshot, detect_drift,
    compute_importance, select_features,
)
from backend.ai import feature_research                                                     # noqa: E402


OUT_INTEL     = _ROOT / "reports" / "feature_intelligence.json"
OUT_SUMMARY   = _ROOT / "reports" / "feature_intelligence_summary.json"
OUT_RESEARCH  = _ROOT / "reports" / "ai_feature_research.json"
OUT_SELECTED  = _ROOT / "reports" / "selected_features.json"


def _stringify(v):
    if isinstance(v, dict):    return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_stringify(x) for x in v]
    if isinstance(v, (date, datetime)): return v.isoformat()
    return v


def _as_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _stringify(v) for k, v in asdict(obj).items()}
    return _stringify(obj)


def main() -> int:
    now = datetime.now(timezone.utc)
    asof = now.date()

    print("=" * 70); print("  AEGIS INDIA · Feature Intelligence (Sprint 2.6)"); print("=" * 70)

    # Latest snapshot + prior snapshot (for drift)
    snaps = list_snapshots(_ROOT, "india")
    if not snaps:
        print("  no feature store snapshot found — run feature_store first"); return 1
    latest = snaps[-1]
    prior = snaps[-2] if len(snaps) >= 2 else None
    print(f"  latest snapshot: {latest.isoformat()}   prior: {prior.isoformat() if prior else '—'}")

    df = read_snapshot(_ROOT, "india", latest)
    if df is None or df.empty:
        print("  snapshot empty — nothing to analyse"); return 1

    # 1) Governance
    gov = validate_governance(asof)
    print(f"  governance:   verdict={gov.verdict}  n={gov.n_features}  active={gov.n_active}  "
          f"missing_rationale={len(gov.missing_rationale)}  missing_intuition={len(gov.missing_intuition)}")

    # 2) Quality (persist per-feature stats)
    qual = persist_quality_snapshot(_ROOT, "india", latest, df)
    print(f"  quality:      n_features={qual.n_features}  null_pct_overall={qual.null_pct_overall:.1%}")

    # 3) Drift vs prior
    if prior is not None:
        df_prior = read_snapshot(_ROOT, "india", prior)
    else:
        df_prior = None
    drift = detect_drift(df, df_prior, latest, prior)
    print(f"  drift:        verdict={drift.verdict}  stable={drift.n_stable}  minor={drift.n_minor_drift}  "
          f"major={drift.n_major_drift}  scored={drift.n_features_scored}")

    # 4) Importance (label-free + supervised proxy using return_20d_pct as pseudo-target)
    target = df["return_20d_pct"] if "return_20d_pct" in df.columns else None
    imp = compute_importance(df, target=target, asof=asof)
    print(f"  importance:   scored={imp.n_features_scored}  with_labels={imp.with_labels}  "
          f"methods={imp.method_available}")

    # 5) Selection (correlation filter · dedup · rank)
    sel = select_features(df, importance_result=imp, target=target,
                           correlation_threshold=0.90, top_k=None,
                           include_experimental=False)
    print(f"  selection:    {sel.n_input} → {sel.n_selected}  "
          f"(consts={len(sel.removed_constants)}  dupes={len(sel.removed_duplicates)}  "
          f"corr={len(sel.removed_correlated)}  leakage={len(sel.leakage_flagged)})")

    # 6) AI Research Agent
    research = feature_research.run(df, gov, imp, "india", asof, top_k=5)
    print(f"  research:     {research.headline[:80]}")

    # ── Emit
    OUT_INTEL.parent.mkdir(parents=True, exist_ok=True)
    OUT_INTEL.write_text(json.dumps({
        "engine":      "feature_intelligence",
        "version":     "v1.0",
        "market":      "india",
        "run_utc":     now.isoformat(timespec="seconds"),
        "asof":        latest.isoformat(),
        "schema_fingerprint": schema_fingerprint(),
        "governance":  _as_dict(gov),
        "quality":     _as_dict(qual),
        "drift":       _as_dict(drift),
        "importance":  _as_dict(imp),
        "selection":   _as_dict(sel),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_INTEL.relative_to(_ROOT)}")

    # Dashboard-friendly summary
    OUT_SUMMARY.write_text(json.dumps({
        "engine":  "feature_intelligence",
        "market":  "india",
        "asof":    latest.isoformat(),
        "governance_verdict": gov.verdict,
        "governance_coverage_rationale_pct": gov.coverage_rationale_pct,
        "governance_coverage_intuition_pct": gov.coverage_intuition_pct,
        "drift_verdict":  drift.verdict,
        "drift_n_major":  drift.n_major_drift,
        "drift_n_minor":  drift.n_minor_drift,
        "n_selected":     sel.n_selected,
        "n_input":        sel.n_input,
        "n_features_registered": len(FEATURE_REGISTRY),
        "n_deprecated":   gov.n_deprecated,
        "n_experimental": gov.n_experimental,
    }, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_SUMMARY.relative_to(_ROOT)}")

    # Research agent
    OUT_RESEARCH.write_text(json.dumps({
        "engine":  "ai_feature_research",
        "version": "v1.0",
        "market":  "india",
        "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "output":  _as_dict(research),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_RESEARCH.relative_to(_ROOT)}")

    # Selected feature set → the subset downstream engines consume
    OUT_SELECTED.write_text(json.dumps({
        "engine":       "feature_selection",
        "market":       "india",
        "asof":         latest.isoformat(),
        "schema_fingerprint": schema_fingerprint(),
        "n_selected":   sel.n_selected,
        "correlation_threshold": sel.correlation_threshold,
        "selected":     sel.selected,
        "removed_summary": {
            "constants":     len(sel.removed_constants),
            "duplicates":    len(sel.removed_duplicates),
            "correlated":    len(sel.removed_correlated),
            "deprecated":    len(sel.removed_deprecated),
            "experimental":  len(sel.removed_experimental),
            "leakage_flags": len(sel.leakage_flagged),
        },
    }, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_SELECTED.relative_to(_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

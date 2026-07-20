"""AEGIS USA · Feature Intelligence runner (Sprint 2.6, USD)."""
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

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.canonical.model              import USA_PROFILE                                # noqa: E402
from backend.feature_store                 import FEATURE_REGISTRY, schema_fingerprint     # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.feature_intelligence          import (                                          # noqa: E402
    validate_governance, persist_quality_snapshot, detect_drift,
    compute_importance, select_features,
)
from backend.ai import feature_research                                                     # noqa: E402


OUT_INTEL     = _USA / "reports" / "feature_intelligence.json"
OUT_SUMMARY   = _USA / "reports" / "feature_intelligence_summary.json"
OUT_RESEARCH  = _USA / "reports" / "ai_feature_research.json"
OUT_SELECTED  = _USA / "reports" / "selected_features.json"


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

    print("=" * 70); print("  AEGIS USA · Feature Intelligence (Sprint 2.6, USD)"); print("=" * 70)

    snaps = list_snapshots(_ROOT, "usa")
    if not snaps:
        print("  no feature store snapshot found — run feature_store first"); return 1
    latest = snaps[-1]
    prior = snaps[-2] if len(snaps) >= 2 else None
    print(f"  latest: {latest.isoformat()}   prior: {prior.isoformat() if prior else '—'}")

    df = read_snapshot(_ROOT, "usa", latest)
    if df is None or df.empty:
        print("  snapshot empty"); return 1

    gov = validate_governance(asof)
    print(f"  governance:  verdict={gov.verdict}  active={gov.n_active}  "
          f"rationale_cov={gov.coverage_rationale_pct:.1f}%")

    qual = persist_quality_snapshot(_ROOT, "usa", latest, df)
    print(f"  quality:     n_features={qual.n_features}  null_pct={qual.null_pct_overall:.1%}")

    df_prior = read_snapshot(_ROOT, "usa", prior) if prior else None
    drift = detect_drift(df, df_prior, latest, prior)
    print(f"  drift:       verdict={drift.verdict}  scored={drift.n_features_scored}  "
          f"stable={drift.n_stable}  minor={drift.n_minor_drift}  major={drift.n_major_drift}")

    target = df["return_20d_pct"] if "return_20d_pct" in df.columns else None
    imp = compute_importance(df, target=target, asof=asof)
    print(f"  importance:  scored={imp.n_features_scored}  with_labels={imp.with_labels}")

    sel = select_features(df, importance_result=imp, target=target,
                           correlation_threshold=0.90)
    print(f"  selection:   {sel.n_input} → {sel.n_selected}  "
          f"(consts={len(sel.removed_constants)} dupes={len(sel.removed_duplicates)} "
          f"corr={len(sel.removed_correlated)} leakage={len(sel.leakage_flagged)})")

    research = feature_research.run(df, gov, imp, "usa", asof, top_k=5)
    print(f"  research:    {research.headline[:80]}")

    OUT_INTEL.parent.mkdir(parents=True, exist_ok=True)
    OUT_INTEL.write_text(json.dumps({
        "engine":       "feature_intelligence",
        "version":      "v1.0",
        "market":       "usa",
        "run_utc":      now.isoformat(timespec="seconds"),
        "asof":         latest.isoformat(),
        "schema_fingerprint": schema_fingerprint(),
        "governance":   _as_dict(gov),
        "quality":      _as_dict(qual),
        "drift":        _as_dict(drift),
        "importance":   _as_dict(imp),
        "selection":    _as_dict(sel),
    }, indent=2, default=str), encoding="utf-8")

    OUT_SUMMARY.write_text(json.dumps({
        "engine":  "feature_intelligence",
        "market":  "usa",
        "asof":    latest.isoformat(),
        "governance_verdict": gov.verdict,
        "governance_coverage_rationale_pct": gov.coverage_rationale_pct,
        "governance_coverage_intuition_pct": gov.coverage_intuition_pct,
        "drift_verdict": drift.verdict,
        "drift_n_major": drift.n_major_drift,
        "drift_n_minor": drift.n_minor_drift,
        "n_selected":    sel.n_selected,
        "n_input":       sel.n_input,
        "n_features_registered": len(FEATURE_REGISTRY),
        "n_deprecated":   gov.n_deprecated,
        "n_experimental": gov.n_experimental,
    }, indent=2), encoding="utf-8")

    OUT_RESEARCH.write_text(json.dumps({
        "engine": "ai_feature_research", "version": "v1.0",
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": latest.isoformat(),
        "output": _as_dict(research),
    }, indent=2, default=str), encoding="utf-8")

    OUT_SELECTED.write_text(json.dumps({
        "engine": "feature_selection", "market": "usa",
        "asof": latest.isoformat(),
        "schema_fingerprint": schema_fingerprint(),
        "n_selected": sel.n_selected,
        "correlation_threshold": sel.correlation_threshold,
        "selected": sel.selected,
        "removed_summary": {
            "constants":     len(sel.removed_constants),
            "duplicates":    len(sel.removed_duplicates),
            "correlated":    len(sel.removed_correlated),
            "deprecated":    len(sel.removed_deprecated),
            "experimental":  len(sel.removed_experimental),
            "leakage_flags": len(sel.leakage_flagged),
        },
    }, indent=2), encoding="utf-8")
    print(f"  wrote 4 files under usa/reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

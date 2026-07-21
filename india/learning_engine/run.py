"""AEGIS India · Learning Engine runner (Sprint 6).

Consumes:
  reports/recommendation_history.parquet  (append-only ledger, may be empty)
  data/raw/india/{TICKER}_D1.parquet      (for outcome computation)
  reports/learning_corpus.parquet         (append-only, may be empty)
  configs/learning_config.yaml

Emits:
  reports/learning_corpus.parquet         (append-only; natural key: market+ticker+rec_asof)
  reports/feature_attribution.json        (per-feature net_alpha ranking)
  reports/model_attribution.json          (per-model net_alpha ranking)
  reports/failure_clusters.json           (recurring failure patterns)
  reports/confidence_calibration.json     (isotonic-PAV calibration curve)
  reports/ai_learning_narrative.json      (AI Learning Analyst)
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

import yaml                                                                                  # noqa: E402

from backend.canonical.model              import INDIA_PROFILE                              # noqa: E402
from backend.feature_store                 import schema_fingerprint                        # noqa: E402
from backend.learning                     import LearningEngine                             # noqa: E402
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai                          import learning_analyst                            # noqa: E402


OUT_FEAT_ATTR = _ROOT / "reports" / "feature_attribution.json"
OUT_MODEL_ATTR = _ROOT / "reports" / "model_attribution.json"
OUT_CLUSTERS   = _ROOT / "reports" / "failure_clusters.json"
OUT_CALIB      = _ROOT / "reports" / "confidence_calibration.json"
OUT_NARRATIVE  = _ROOT / "reports" / "ai_learning_narrative.json"

CONFIG_PATH   = _ROOT / "configs" / "learning_config.yaml"


def _stringify(v):
    if isinstance(v, dict):    return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_stringify(x) for x in v]
    if isinstance(v, (date, datetime)): return v.isoformat()
    if hasattr(v, "value"):    return v.value
    return v


def _as_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _stringify(v) for k, v in asdict(obj).items()}
    return _stringify(obj)


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70); print("  AEGIS INDIA · Learning Engine v1 (Sprint 6)"); print("=" * 70)

    cfg_all = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    cfg = (cfg_all.get("market_defaults") or {}).get("india", {})
    horizon_days = int(cfg.get("horizon_days", 60))
    min_cluster  = int(cfg.get("min_cluster_size", 3))
    n_bins       = int(cfg.get("n_calibration_bins", 10))
    print(f"  config: horizon={horizon_days}d · min_cluster={min_cluster} · n_bins={n_bins}")

    # Register model
    model_id = "aegis.learning.v1"
    register_model(_ROOT,
        model_id=model_id, engine="learning_engine",
        market="india", version="1.0.0",
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by india/learning_engine on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, model_id)

    engine = LearningEngine(
        repo_root=_ROOT, market="india",
        horizon_days=horizon_days,
        min_cluster_size=min_cluster,
        n_calibration_bins=n_bins,
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
    )
    result = engine.run(asof=now.date())
    print(f"  recs in history:  {result.n_recs_in_history}")
    print(f"  new closed today: {result.n_new_closed}")
    print(f"  corpus total:     {result.n_corpus_total}  (winners={result.n_winners}, losers={result.n_losers})")
    print(f"  win rate:         {result.win_rate}  · avg return: {result.avg_return}")
    print(f"  attributions:     features={len(result.feature_attribution)} · models={len(result.model_attribution)}")
    print(f"  failure clusters: {len(result.failure_clusters)}")
    print(f"  calibration:      {result.calibration_curve.method}  n_obs={result.calibration_curve.n_observations}")

    # Emit outputs
    OUT_FEAT_ATTR.parent.mkdir(parents=True, exist_ok=True)
    OUT_FEAT_ATTR.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof": result.asof.isoformat(),
        "n_features_scored": len(result.feature_attribution),
        "attribution": [_as_dict(a) for a in result.feature_attribution[:100]],
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    OUT_MODEL_ATTR.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof": result.asof.isoformat(),
        "n_models_scored": len(result.model_attribution),
        "attribution": [_as_dict(a) for a in result.model_attribution],
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    OUT_CLUSTERS.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof": result.asof.isoformat(),
        "n_clusters": len(result.failure_clusters),
        "clusters": [_as_dict(c) for c in result.failure_clusters],
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    OUT_CALIB.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof": result.asof.isoformat(),
        "calibration_curve": _as_dict(result.calibration_curve) if result.calibration_curve else None,
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    # Sprint 7.5 · append learning summary to permanent history (fail-open)
    try:
        from backend.persistence import append_snapshot_row
        _hist_payload = {
            "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
            "market": "india", "run_utc": now.isoformat(timespec="seconds"),
            "asof": result.asof.isoformat(),
            "n_feature_attribution": len(result.feature_attribution),
            "n_model_attribution":   len(result.model_attribution),
            "n_failure_clusters":    len(result.failure_clusters),
            "has_calibration":       result.calibration_curve is not None,
            "model_stamp": model_stamp,
        }
        append_snapshot_row(_hist_payload, _ROOT / "reports" / "learning_history.parquet")
    except Exception as _hist_err:
        print(f"  history append warning (non-fatal): {_hist_err}")

    # AI narrative
    ai = learning_analyst.run(result, "india", result.asof)
    OUT_NARRATIVE.write_text(json.dumps({
        "engine": "ai_learning_narrative", "version": "v1.0",
        "market": "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof": result.asof.isoformat(),
        "output": _as_dict(ai),
    }, indent=2, default=str), encoding="utf-8")

    print(f"  wrote 5 files under reports/ (feature_attribution, model_attribution,")
    print(f"        failure_clusters, confidence_calibration, ai_learning_narrative)")
    print(f"  ai headline: {ai.headline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

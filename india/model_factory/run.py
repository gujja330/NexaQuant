"""AEGIS India · Model Factory runner (Sprint 2.7).

Reads: features/india/{latest}.parquet (Feature Store)
       reports/selected_features.json (Feature Intelligence)
Runs:  every registered model → predictions + metrics + AI analyst → ensemble
Emits: reports/model_factory.json          full engine + all model predictions
       reports/model_metrics.json           per-model metrics
       reports/ensemble.json                aggregated ensemble scoreboard
       reports/ai_model_narrative.json      AI Model Analyst output
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

from backend.canonical.model            import INDIA_PROFILE                                # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.feature_store              import schema_fingerprint                            # noqa: E402
from backend.model_factory              import (                                              # noqa: E402
    ModelFactory, ensemble_predict, evaluate_model, EnsembleWeights,
)
from backend.model_registry.registry    import register_model, ModelStatus                 # noqa: E402
from backend.ai                         import model_analyst                                # noqa: E402


OUT_FACTORY    = _ROOT / "reports" / "model_factory.json"
OUT_METRICS    = _ROOT / "reports" / "model_metrics.json"
OUT_ENSEMBLE   = _ROOT / "reports" / "ensemble.json"
OUT_NARRATIVE  = _ROOT / "reports" / "ai_model_narrative.json"
SELECTED_FEATS = _ROOT / "reports" / "selected_features.json"
LEARNING_CORPUS = _ROOT / "reports" / "learning.parquet"


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
    print("=" * 70); print("  AEGIS INDIA · Model Factory (Sprint 2.7)"); print("=" * 70)

    snaps = list_snapshots(_ROOT, "india")
    if not snaps:
        print("  no feature store snapshot found — run feature_store first"); return 1
    latest = snaps[-1]
    df = read_snapshot(_ROOT, "india", latest)
    if df is None or df.empty:
        print("  snapshot empty"); return 1

    # Only keep selected features + identity + target proxy
    selected = []
    if SELECTED_FEATS.exists():
        try:
            selected = json.loads(SELECTED_FEATS.read_text(encoding="utf-8")).get("selected", [])
        except Exception:
            pass
    identity_cols = {"market", "ticker", "asof", "sector", "currency"}
    # Ensemble/model runners need identity + selected + return_20d_pct (for metrics)
    keep_cols = identity_cols | set(selected) | {"return_20d_pct"}
    keep_cols &= set(df.columns)
    if not selected:
        # If Feature Intelligence hasn't run yet, allow all — but warn
        keep_cols = set(df.columns)
        print("  WARN: no selected_features.json — using full feature vector")
    df_sub = df[[c for c in df.columns if c in keep_cols]]
    print(f"  snapshot: {latest.isoformat()}   rows={len(df_sub)}   features={len(df_sub.columns)}")
    print(f"  selected feature subset in use: {len(selected)} features")

    # Build factory + run all models
    factory = ModelFactory(_ROOT, "india")
    factory.train_all(df_sub, target=None, cutoff=latest)   # rule-based, no-op train
    predictions = factory.predict_all(df_sub, cutoff=latest)
    print(f"  ran {len(predictions)} models")

    # Compute per-model metrics
    metrics_list = [evaluate_model(p, learning_corpus_path=LEARNING_CORPUS)
                     for p in predictions]

    # Ensemble (equal-weight v0)
    ens = ensemble_predict(predictions, weights=None, market="india", asof=latest)
    print(f"  ensemble: {ens.n_models} models · {len(ens.predictions)} tickers scored")

    # Register each model in the model registry (marks all as EXPERIMENTAL until approved)
    for m in factory.models:
        register_model(_ROOT,
            model_id=m.metadata.model_id, engine="model_factory",
            market="india", version=m.metadata.version,
            feature_set_version=schema_fingerprint(),
            schema_version=schema_fingerprint(),
            approval_status=ModelStatus.EXPERIMENTAL,
            notes=f"registered by india/model_factory/run.py on {now.date().isoformat()}")

    # AI Model Analyst
    desc = factory.describe_all()
    ai_out = model_analyst.run(desc, metrics_list,
                                  ensemble_summary={"strategy": ens.strategy,
                                                       "n_models": ens.n_models},
                                  market_name="india", asof=latest)

    # ── Emit outputs ────────────────────────────────────────
    OUT_FACTORY.parent.mkdir(parents=True, exist_ok=True)
    OUT_FACTORY.write_text(json.dumps({
        "engine":  "model_factory", "version": "v1.0",
        "market":  "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "schema_fingerprint": schema_fingerprint(),
        "n_models": len(factory.models),
        "models":   desc,
        "predictions_summary": [{
            "model_id": p.model_id, "n_scored": p.n_scored,
            "notes":    p.notes,
            "top_5": [
                {"ticker": str(r["ticker"]), "score": float(r["score"]),
                 "confidence": float(r["confidence"])}
                for _, r in p.predictions.sort_values("score", ascending=False).head(5).iterrows()
            ],
        } for p in predictions],
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_FACTORY.relative_to(_ROOT)}")

    OUT_METRICS.write_text(json.dumps({
        "engine": "model_intelligence", "market": "india",
        "asof": latest.isoformat(),
        "n_models": len(metrics_list),
        "metrics": [_as_dict(m) for m in metrics_list],
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_METRICS.relative_to(_ROOT)}")

    OUT_ENSEMBLE.write_text(json.dumps({
        "engine":   "ensemble", "market": "india",
        "asof":     latest.isoformat(),
        "strategy": ens.strategy,
        "weights":  ens.weights,
        "n_models": ens.n_models,
        "top_10":   [
            {"ticker": str(r["ticker"]),
             "ensemble_score": float(r["ensemble_score"]),
             "ensemble_confidence": float(r["ensemble_confidence"]),
             "n_models_scoring": int(r["n_models_scoring"]),
             "per_model_score": r["per_model_score"]}
            for _, r in ens.predictions.head(10).iterrows()
        ],
        "bottom_5": [
            {"ticker": str(r["ticker"]),
             "ensemble_score": float(r["ensemble_score"]),
             "ensemble_confidence": float(r["ensemble_confidence"])}
            for _, r in ens.predictions.tail(5).iterrows()
        ],
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_ENSEMBLE.relative_to(_ROOT)}")

    OUT_NARRATIVE.write_text(json.dumps({
        "engine":  "ai_model_narrative", "version": "v1.0",
        "market":  "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "output":  _as_dict(ai_out),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_NARRATIVE.relative_to(_ROOT)}")

    print(f"  headline: {ai_out.headline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

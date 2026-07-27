"""AEGIS USA · Model Factory runner (Sprint 2.7, USD)."""
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

from backend.canonical.model            import USA_PROFILE                                  # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.feature_store              import schema_fingerprint                            # noqa: E402
from backend.model_factory              import (                                              # noqa: E402
    ModelFactory, ensemble_predict, evaluate_model, EnsembleWeights,
)
from backend.model_registry.registry    import register_model, ModelStatus                 # noqa: E402
from backend.ai                         import model_analyst                                # noqa: E402
from backend.certification.adaptive_weights import load_ensemble_weights_config              # noqa: E402


OUT_FACTORY    = _USA / "reports" / "model_factory.json"
OUT_METRICS    = _USA / "reports" / "model_metrics.json"
OUT_ENSEMBLE   = _USA / "reports" / "ensemble.json"
OUT_NARRATIVE  = _USA / "reports" / "ai_model_narrative.json"
SELECTED_FEATS = _USA / "reports" / "selected_features.json"
LEARNING_CORPUS = _USA / "reports" / "learning.parquet"
ADAPTIVE_WEIGHTS_CFG = _USA / "configs" / "ensemble_weights_adaptive.yaml"


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
    print("=" * 70); print("  AEGIS USA · Model Factory (Sprint 2.7, USD)"); print("=" * 70)

    snaps = list_snapshots(_ROOT, "usa")
    if not snaps:
        print("  no feature store snapshot found"); return 1
    latest = snaps[-1]
    df = read_snapshot(_ROOT, "usa", latest)
    if df is None or df.empty:
        print("  snapshot empty"); return 1

    selected: list[str] = []
    if SELECTED_FEATS.exists():
        try:
            selected = json.loads(SELECTED_FEATS.read_text(encoding="utf-8")).get("selected", [])
        except Exception:
            pass
    identity_cols = {"market", "ticker", "asof", "sector", "currency"}
    keep_cols = identity_cols | set(selected) | {"return_20d_pct"}
    keep_cols &= set(df.columns)
    if not selected:
        keep_cols = set(df.columns)
        print("  WARN: no selected_features.json — using full feature vector")
    df_sub = df[[c for c in df.columns if c in keep_cols]]
    print(f"  snapshot: {latest.isoformat()}   rows={len(df_sub)}   features={len(df_sub.columns)}")

    factory = ModelFactory(_ROOT, "usa")
    factory.train_all(df_sub, target=None, cutoff=latest)
    predictions = factory.predict_all(df_sub, cutoff=latest)
    print(f"  ran {len(predictions)} models")

    metrics_list = [evaluate_model(p, learning_corpus_path=LEARNING_CORPUS)
                     for p in predictions]
    # Adaptive weights (historical IC → tomorrow's ensemble) · Article 100 L4
    # Fallback lookups: usa/configs first, then repo-root configs (India shares).
    adaptive = load_ensemble_weights_config(ADAPTIVE_WEIGHTS_CFG) or \
                 load_ensemble_weights_config(_ROOT / "configs" / "ensemble_weights_adaptive.yaml")
    if adaptive:
        ens_weights = EnsembleWeights(weights=adaptive, strategy="adaptive_ic_weighted")
        print(f"  ensemble weights: adaptive · {len(adaptive)} models · "
              f"max={max(adaptive.values()):.4f} min={min(adaptive.values()):.4f}")
    else:
        ens_weights = None
        print("  ensemble weights: equal_weight (adaptive config missing/invalid)")
    ens = ensemble_predict(predictions, weights=ens_weights, market="usa", asof=latest)
    print(f"  ensemble: {ens.n_models} models · {len(ens.predictions)} tickers · strategy={ens.strategy}")

    for m in factory.models:
        register_model(_ROOT,
            model_id=m.metadata.model_id, engine="model_factory",
            market="usa", version=m.metadata.version,
            feature_set_version=schema_fingerprint(),
            schema_version=schema_fingerprint(),
            approval_status=ModelStatus.EXPERIMENTAL,
            notes=f"registered by usa model_factory on {now.date().isoformat()}")

    desc = factory.describe_all()
    ai_out = model_analyst.run(desc, metrics_list,
                                  ensemble_summary={"strategy": ens.strategy,
                                                       "n_models": ens.n_models},
                                  market_name="usa", asof=latest)

    OUT_FACTORY.parent.mkdir(parents=True, exist_ok=True)
    OUT_FACTORY.write_text(json.dumps({
        "engine": "model_factory", "version": "v1.0",
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof":   latest.isoformat(),
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

    OUT_METRICS.write_text(json.dumps({
        "engine": "model_intelligence", "market": "usa",
        "asof":   latest.isoformat(),
        "n_models": len(metrics_list),
        "metrics": [_as_dict(m) for m in metrics_list],
    }, indent=2, default=str), encoding="utf-8")

    OUT_ENSEMBLE.write_text(json.dumps({
        "engine":   "ensemble", "market": "usa",
        "asof":     latest.isoformat(),
        "strategy": ens.strategy, "weights": ens.weights,
        "n_models": ens.n_models,
        "top_10": [
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

    OUT_NARRATIVE.write_text(json.dumps({
        "engine":  "ai_model_narrative", "version": "v1.0",
        "market":  "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "output":  _as_dict(ai_out),
    }, indent=2, default=str), encoding="utf-8")

    print(f"  wrote 4 files under usa/reports/")
    print(f"  headline: {ai_out.headline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

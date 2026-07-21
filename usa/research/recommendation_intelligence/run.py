"""AEGIS USA · Recommendation Intelligence v3 runner (Sprint 3, USD)."""
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
from backend.feature_store                 import schema_fingerprint                        # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.recommendation               import RecommendationEngine                       # noqa: E402
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai import recommendation_analyst                                                # noqa: E402


OUT_FULL      = _USA / "reports" / "recommendations_v3.json"
OUT_SUMMARY   = _USA / "reports" / "recommendations_v3_summary.json"
OUT_CONFLICTS = _USA / "reports" / "recommendations_v3_conflicts.json"
OUT_NARRATIVE = _USA / "reports" / "ai_recommendation_narrative.json"

ENSEMBLE_PATH  = _USA / "reports" / "ensemble.json"
MI_SUMMARY     = _USA / "reports" / "market_intelligence_summary.json"
SELECTED_FEATS = _USA / "reports" / "selected_features.json"


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
    print("=" * 70)
    print("  AEGIS USA · Recommendation Intelligence v3 (Sprint 3, USD)")
    print("=" * 70)

    if not ENSEMBLE_PATH.exists():
        print("  FATAL: usa/reports/ensemble.json not found — run model_factory first"); return 1
    ens = json.loads(ENSEMBLE_PATH.read_text(encoding="utf-8"))
    ens_rows = list(ens.get("top_10", [])) + list(ens.get("bottom_5", []))
    seen = set(); dedup = []
    for r in ens_rows:
        t = r.get("ticker")
        if t and t not in seen:
            seen.add(t); dedup.append(r)
    ens_rows = dedup
    print(f"  ensemble rows: {len(ens_rows)}")

    regime = "unknown"
    if MI_SUMMARY.exists():
        try:
            regime = json.loads(MI_SUMMARY.read_text(encoding="utf-8")).get("regime", "unknown")
        except Exception: pass
    print(f"  regime: {regime}")

    selected: list[str] = []
    if SELECTED_FEATS.exists():
        try:
            selected = json.loads(SELECTED_FEATS.read_text(encoding="utf-8")).get("selected", [])
        except Exception: pass
    print(f"  selected features: {len(selected)}")

    snaps = list_snapshots(_ROOT, "usa")
    if not snaps: print("  FATAL: no snapshot"); return 1
    latest = snaps[-1]
    df = read_snapshot(_ROOT, "usa", latest)
    if df is None or df.empty: print("  FATAL: snapshot empty"); return 1
    print(f"  snapshot: {latest.isoformat()} · rows={len(df)}")

    model_id = "aegis.recommendation.v3"
    register_model(_ROOT,
        model_id=model_id, engine="recommendation_intelligence",
        market="usa", version="1.0.0",
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by usa/recommendation_intelligence on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, model_id)

    engine = RecommendationEngine(
        repo_root=_ROOT, market="usa", regime=regime,
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
        model_stamp=model_stamp,
    )
    batch = engine.run(
        ensemble_top_rows=ens_rows, features_df=df,
        selected_features=selected, asof=latest,
    )
    print(f"  n_tickers: {batch.n_tickers}")
    print(f"    STRONG_BUY : {batch.n_strong_buy}  BUY: {batch.n_buy}")
    print(f"    HOLD       : {batch.n_hold}")
    print(f"    SELL       : {batch.n_sell}  STRONG_SELL: {batch.n_strong_sell}")
    print(f"    conflicts collapsed to HOLD: {batch.n_disagreement}")

    OUT_FULL.parent.mkdir(parents=True, exist_ok=True)
    OUT_FULL.write_text(json.dumps({
        "engine":  batch.engine, "version": batch.version, "market": batch.market,
        "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "currency": USA_PROFILE.currency,
        "regime":  regime,
        "n_tickers": batch.n_tickers,
        "distribution": {
            "STRONG_BUY":  batch.n_strong_buy, "BUY": batch.n_buy,
            "HOLD":        batch.n_hold,      "SELL": batch.n_sell,
            "STRONG_SELL": batch.n_strong_sell,
        },
        "n_disagreement_collapsed": batch.n_disagreement,
        "recommendations": [_as_dict(r) for r in batch.recommendations],
        "notes":  batch.notes,
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    # Sprint 7.5 · append to permanent history (fail-open)
    try:
        from backend.persistence import append_snapshot_row
        append_snapshot_row(json.loads(OUT_FULL.read_text(encoding="utf-8")),
                             _ROOT / "usa" / "reports" / "recommendation_history.parquet")
    except Exception as _hist_err:
        print(f"  history append warning (non-fatal): {_hist_err}")

    OUT_SUMMARY.write_text(json.dumps({
        "engine":  batch.engine, "market": batch.market,
        "asof":    latest.isoformat(),
        "regime":  regime,
        "n_tickers": batch.n_tickers,
        "distribution": {
            "STRONG_BUY":  batch.n_strong_buy, "BUY": batch.n_buy,
            "HOLD":        batch.n_hold,      "SELL": batch.n_sell,
            "STRONG_SELL": batch.n_strong_sell,
        },
        "n_disagreement": batch.n_disagreement,
        "top_buys": [
            {"ticker": r.ticker, "action": r.action.value,
             "score": r.ensemble_score, "confidence": r.regime_adjusted_confidence}
            for r in sorted(
                [x for x in batch.recommendations if x.action.value in ("STRONG_BUY", "BUY")],
                key=lambda x: x.regime_adjusted_confidence, reverse=True)[:10]
        ],
        "top_sells": [
            {"ticker": r.ticker, "action": r.action.value,
             "score": r.ensemble_score, "confidence": r.regime_adjusted_confidence}
            for r in sorted(
                [x for x in batch.recommendations if x.action.value in ("STRONG_SELL", "SELL")],
                key=lambda x: x.regime_adjusted_confidence, reverse=True)[:10]
        ],
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    OUT_CONFLICTS.write_text(json.dumps({
        "engine": batch.engine, "market": batch.market, "asof": latest.isoformat(),
        "n_conflicts": len(batch.conflicts),
        "conflicts":   batch.conflicts,
    }, indent=2, default=str), encoding="utf-8")

    analyst = recommendation_analyst.run(batch, regime, "usa", latest)
    OUT_NARRATIVE.write_text(json.dumps({
        "engine":  "ai_recommendation_narrative", "version": "v1.0",
        "market":  "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "output":  _as_dict(analyst),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote 4 files under usa/reports/")
    print(f"  ai headline: {analyst.headline}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

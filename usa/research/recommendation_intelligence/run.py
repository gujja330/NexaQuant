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

# CEO 2026-11-04 · report writes honour AEGIS_OUT_ROOT so a test can
# run this engine as a subprocess without touching live artifacts.
# CEO 2026-11-04 v2 · _USA stays the REAL directory because the
# engines READ their upstream inputs through it (selected_features,
# learning.parquet, sized_positions, configs). Redirecting it broke
# the chain: portfolio_engine exited 1 with "usa/reports/
# sized_positions.json missing" because risk_engine's output was
# being looked for in the empty tmp root. Only WRITES move.
from backend.shared.out_root import resolved_out_root  # noqa: E402
_OUT = resolved_out_root(_ROOT)
_USA_OUT = _OUT / "usa"

from backend.canonical.model              import USA_PROFILE                                # noqa: E402
from backend.feature_store                 import schema_fingerprint                        # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.recommendation               import RecommendationEngine                       # noqa: E402
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai import recommendation_analyst                                                # noqa: E402


OUT_FULL      = _USA_OUT / "reports" / "recommendations_v3.json"
OUT_SUMMARY   = _USA_OUT / "reports" / "recommendations_v3_summary.json"
OUT_CONFLICTS = _USA_OUT / "reports" / "recommendations_v3_conflicts.json"
OUT_NARRATIVE = _USA_OUT / "reports" / "ai_recommendation_narrative.json"

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


def _history_fatal(market: str, detail: str) -> None:
    """Record that an upstream precondition killed this run.

    CEO 2026-11-03 · the recommendation step is "optional": True in the
    orchestrator, so returning 1 from here leaves the daily run GREEN. The
    orchestrator's tolerance is deliberate and stays; what must not stay is
    the silence. A FATAL exit now leaves a state file saying history was
    expected and did not happen, which the strict checker fails on.
    """
    try:
        from backend.persistence import record_not_attempted, REASON_UPSTREAM_FATAL
        record_not_attempted(_ROOT, market, reason=REASON_UPSTREAM_FATAL,
                             detail=detail, expected=True)
    except Exception:
        pass


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70)
    print("  AEGIS USA · Recommendation Intelligence v3 (Sprint 3, USD)")
    print("=" * 70)

    if not ENSEMBLE_PATH.exists():
        print("  FATAL: usa/reports/ensemble.json not found — run model_factory first")
        _history_fatal("usa", "usa/reports/ensemble.json not found"); return 1
    ens = json.loads(ENSEMBLE_PATH.read_text(encoding="utf-8"))
    # ── FULL UNIVERSE · CEO 2026-09-09 ──────────────────────────────
    #
    # This read top_10 + bottom_5, so the recommendation engine only ever
    # judged 15 of the scored universe. Everything else was discarded
    # before any rule saw it - COP, DVN, MPC and TRV cleared every gate at
    # confidence 0.6045 and simply never appeared. The workbook that
    # resulted looked correct, which is precisely why it went unnoticed.
    #
    # `all_candidates` carries the whole universe; the 15-row slice is
    # kept as a fallback for an ensemble.json written before this change.
    ens_rows = list(ens.get("all_candidates") or [])
    if not ens_rows:
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
    if not snaps:
        print("  FATAL: no snapshot")
        _history_fatal("usa", "no feature store snapshot"); return 1
    latest = snaps[-1]
    df = read_snapshot(_ROOT, "usa", latest)
    if df is None or df.empty:
        print("  FATAL: snapshot empty")
        _history_fatal("usa", "feature store snapshot empty"); return 1
    print(f"  snapshot: {latest.isoformat()} · rows={len(df)}")

    model_id = "aegis.recommendation.v3"
    register_model(_OUT,
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
    # CEO 2026-11-03 · verified append · see the India runner for why. USA
    # accumulated 4 daily rows in eight months; 135 of its 139 came from one
    # replay batch on 2026-07-21.
    try:
        from backend.persistence import append_and_record
        # CEO 2026-11-07 · the history append was the ONE write this
        # runner did not redirect. Sprint-2 isolation moved every report
        # output to _OUT and left this on _ROOT, so each regression run
        # appended a row to the LIVE ledger. Measured: running
        # backend/tests/test_sprint3.py changed
        # reports/recommendation_history.parquet and its USA twin on
        # every invocation, engine=aegis.recommendation.v3.
        # Production sets no variable, so _OUT == _ROOT and the live
        # ledger still receives the real daily row.
        _hist_state = append_and_record(
            json.loads(OUT_FULL.read_text(encoding="utf-8")),
            _USA_OUT / "reports" / "recommendation_history.parquet",
            root=_OUT, market="usa")
        print(f"  history: {_hist_state['state']} · {_hist_state['detail']} "
              f"(rows {_hist_state['rows_before']} -> "
              f"{_hist_state.get('rows_after')})")
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

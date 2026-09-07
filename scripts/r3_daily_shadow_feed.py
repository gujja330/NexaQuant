"""AEGIS · R3 CANONICAL DAILY SHADOW FEED · Lane A + Lane C.

CEO 2026-09-07 · "Start daily PIT accumulation immediately" and "Run
forward validation continuously from today". This is the producer that
does both. It is the ONLY canonical R3 daily entry point;
`backend/recommendation/runner3/` is retained for its risk fields and
comparator only, pending port.

WHAT THE 2026-09-07 REWRITE FIXED
---------------------------------
The previous version could never start the evidence clock:

1 · IT BLOCKED ON TRAINING. `if train_summary.status != TRAINED: return
    TRAIN_SKIPPED` · and training now correctly reports
    INSUFFICIENT_SAMPLE, because the dataset is a single cross-section
    (India 24 rows/3 dates, USA 500 rows/2 dates). So the feed wrote
    nothing, which meant no accumulation, which meant the dataset stayed
    a single cross-section. A deadlock: the fix for the blocker was
    gated on the blocker.

2 · IT SCORED HISTORY, NOT TODAY. It took `groupby("ticker").tail(1)` of
    the OUTCOME dataset · i.e. rows for already-CLOSED trades · and
    called the result "today's picks". Re-scoring closed history is not a
    forward prediction and can never be prospective evidence.

THE TWO JOBS, SEPARATED
-----------------------
LANE A · PIT SUBSTRATE. Recorded EVERY day for EVERY ELIGIBLE NAME in the
PRODUCTION UNIVERSE (India 50 · USA 516), whether or not a model exists.
This is what eventually gives walk-forward the time dispersion it
currently lacks · each day adds one distinct entry date. Not writing it
because no model had trained is precisely what kept the dataset a single
cross-section.

CEO 2026-09-07 · LANE A UNIVERSE DECISION. Lane A previously drew from
the R2 recommendations SSoT, which publishes only the top 15 names per
market. `top_n` was never the binding constraint - the SOURCE was. Left
alone, thirty days would have produced thousands of rows that were still
a SELECTION-BIASED sample concentrated on R2's preferred names, and any
model trained on it would have learned R2's selection rather than the
market. Lane A now draws the full eligible production universe so the
training substrate is broad; Lane C's prediction selection stays separate
and is recorded per row, so the two can never be conflated in analysis.

LANE C · FORWARD PREDICTION. Written only when a trained, serialized
artifact exists. When none does, the prediction fields are
NOT_AVAILABLE_AT_ASOF and the action is NO_MODEL · never a fabricated
probability. The feature snapshot and the R2 comparator are still
recorded, so the day is not lost.

ISOLATION · reads R2 outputs READ-ONLY (permitted by the PDF) and writes
ONLY to reports/research/r3/. Never the Registry, never the workbook.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

NOT_AVAILABLE = "NOT_AVAILABLE_AT_ASOF"


def _eligible_universe(root: Path, market: str) -> list:
    """The FULL production universe · Lane A substrate scope.

    Source of truth is configs/aegis_universes.yaml -> markets.<m>.source_file
    (reports/india_universe.json · usa/reports/universe.json). This is the
    same universe R2 is permitted to trade, so Lane A observes exactly the
    opportunity set, not a subset of it.
    """
    try:
        import yaml
        cfg = yaml.safe_load(
            (root / "configs" / "aegis_universes.yaml").read_text(encoding="utf-8")) or {}
        src = ((cfg.get("markets") or {}).get(market.lower()) or {}).get("source_file")
        if not src:
            return []
        p = root / src
        if not p.exists():
            return []
        d = json.loads(p.read_text(encoding="utf-8"))
        out = []
        for t in (d.get("tickers") or []):
            tk = str(t.get("symbol") if isinstance(t, dict) else t).upper().split(".", 1)[0]
            if tk:
                out.append(tk)
        return sorted(set(out))
    except Exception:
        return []


def _r2_universe(root: Path, market: str) -> list:
    """Today's eligible names + R2's own view · READ-ONLY comparator source.

    reports/recommendations.json (India) and usa/reports/recommendations.json
    (USA) are the canonical SSoT recommendation artifacts.
    """
    p = (root / "usa" / "reports" / "recommendations.json"
         if market.lower() == "usa"
         else root / "reports" / "recommendations.json")
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in (d.get("recommendations") or []):
        tk = str(r.get("ticker") or "").upper().split(".", 1)[0]
        if not tk:
            continue
        out.append({
            "ticker": tk,
            "sector": r.get("sector"),
            "r2_score": r.get("composite_decision_score"),
            "r2_action": r.get("action") or r.get("recommendation"),
            "r2_confidence": r.get("confidence"),
            "r2_rank": r.get("rank"),
        })
    return out


def _pit_features(root: Path, market: str, ticker: str, asof: str) -> dict:
    """Tier-1 PIT feature snapshot for one name, as of `asof`.

    Only TIER1_SCOPE features are considered · the F01-F05 fundamentals
    substrate is excluded by contract, not by omission. A feature with no
    knowable value today is simply absent from the snapshot; it is never
    imputed from a later observation.
    """
    from backend.research.r3.tier1_gbm import TIER1_SCOPE

    feats = {}
    # Signal-ledger technicals · derived from the R2 recommendation record
    # for this asof, which IS point-in-time (it is today's own output).
    rec = _rec_by_ticker(root, market).get(ticker) or {}
    mapping = {
        "entry_signal_score": rec.get("ensemble_score"),
        "entry_calibrated_conf": rec.get("calibrated_confidence"),
        "entry_regime_adj_conf": rec.get("regime_adjusted_confidence"),
        "entry_model_agreement": rec.get("model_agreement"),
        "entry_n_models_scoring": rec.get("n_models_scoring"),
    }
    for k in TIER1_SCOPE:
        v = mapping.get(k)
        if v is None:
            continue
        try:
            feats[k] = float(v)
        except (TypeError, ValueError):
            continue
    return feats


_REC_CACHE: dict = {}


def _rec_by_ticker(root: Path, market: str) -> dict:
    key = (str(root), market)
    if key in _REC_CACHE:
        return _REC_CACHE[key]
    p = (root / "usa" / "reports" / "recommendations.json"
         if market.lower() == "usa"
         else root / "reports" / "recommendations.json")
    out = {}
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for r in (d.get("recommendations") or []):
                tk = str(r.get("ticker") or "").upper().split(".", 1)[0]
                if tk:
                    out[tk] = r
        except Exception:
            pass
    _REC_CACHE[key] = out
    return out


def _close_at(root: Path, market: str, ticker: str, asof: str):
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, ticker)
        if not p or not p.exists():
            return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        t = pd.to_datetime(asof).normalize()
        m = df.index <= t
        if not m.any():
            return None
        col = "close" if "close" in df.columns else "Close"
        return float(df.loc[m, col].iloc[-1])
    except Exception:
        return None


def run_daily_shadow(root: Path, market: str, asof: str,
                     top_n: int = 25) -> dict:
    """One daily cycle · PIT snapshot always, prediction when a model exists."""
    from backend.research.r3.shadow_ledger import append_shadow_pick
    from backend.research.r3.tier1_gbm import (
        MODEL_VERSION, FEATURE_VERSION, CALIBRATOR_VERSION, load_model,
        apply_platt)

    # LANE A scope · every eligible production-universe name.
    eligible = _eligible_universe(root, market)
    # LANE C scope · R2's own selection, kept SEPARATE and recorded per
    # row so a later analysis can always tell the broad substrate apart
    # from the R2-selected subset.
    r2_rows = {r["ticker"]: r for r in _r2_universe(root, market)}
    if not eligible:
        # Fall back to the R2 selection ONLY if the production universe
        # file is unreadable · and say so, rather than silently narrowing.
        eligible = sorted(r2_rows)
        _scope = "R2_SELECTION_FALLBACK"
    else:
        _scope = "PRODUCTION_UNIVERSE"
    if not eligible:
        return {"market": market, "asof": asof, "status": "NO_UNIVERSE",
                "reason": "production universe and recommendations both empty"}

    model, calibrator, model_feats = load_model(root, market)
    have_model = model is not None

    n_written = 0
    n_snapshot_only = 0
    n_r2_selected = 0
    n_with_features = 0
    for tk in eligible:
        row = r2_rows.get(tk, {})
        _is_r2 = tk in r2_rows
        if _is_r2:
            n_r2_selected += 1
        feats = _pit_features(root, market, tk, asof)
        if feats:
            n_with_features += 1
        entry = _close_at(root, market, tk, asof)

        raw_p = cal_p = None
        action = "NO_MODEL"
        if have_model and feats:
            try:
                import pandas as pd
                X = pd.DataFrame([{f: float(feats.get(f) or 0.0)
                                   for f in model_feats}])
                raw_p = float(model.predict_proba(X)[:, 1][0])
                cal_p = apply_platt(calibrator, [raw_p])[0]
                action = ("BUY" if cal_p >= 0.55
                          else "WATCH" if cal_p >= 0.45 else "AVOID")
            except Exception:
                raw_p = cal_p = None
                action = "NO_MODEL"
        if action == "NO_MODEL":
            n_snapshot_only += 1

        append_shadow_pick(
            root, market, tk, asof,
            r3_score=cal_p, r3_calibrated_p=cal_p, action=action,
            features=feats,
            model_id="aegis.r3.gbm_tier1" if have_model else NOT_AVAILABLE,
            r3_raw_p=raw_p, rank=row.get("r2_rank"),
            model_version=MODEL_VERSION if have_model else NOT_AVAILABLE,
            feature_version=FEATURE_VERSION,
            calibrator_version=(CALIBRATOR_VERSION if calibrator is not None
                                else NOT_AVAILABLE),
            entry_price=entry,
            horizon_days=5,          # frozen primary target · R3-1A
            top_features=[],
            regime=NOT_AVAILABLE,
            comparator={
                "r2_score": row.get("r2_score", NOT_AVAILABLE),
                "r2_action": row.get("r2_action", NOT_AVAILABLE),
                "r2_confidence": row.get("r2_confidence", NOT_AVAILABLE),
                # Whether R2 SELECTED this name today · the field that
                # keeps Lane A's broad substrate distinguishable from the
                # R2-selected subset. Training on the substrate without
                # this flag would silently inherit R2's selection.
                "r2_selected_today": _is_r2,
                "r2_in_universe": True,
                "relative_return_pp": "PENDING",
                "rotation_outcome": "PENDING",
            },
        )
        n_written += 1

    return {
        "market": market, "asof": asof, "status": "APPENDED",
        "lane_a_scope": _scope,
        "n_eligible_universe": len(eligible),
        "n_written": n_written,
        "n_r2_selected": n_r2_selected,
        "n_with_tier1_features": n_with_features,
        "n_snapshot_only_no_model": n_snapshot_only,
        "model_available": have_model,
        "lane_a_note": ("PIT feature snapshot recorded for every name · this "
                        "is what builds time dispersion for walk-forward"),
        "lane_c_note": ("forward prediction recorded only when a serialized "
                        "artifact exists · never fabricated"),
        "isolation_note": "writes ONLY reports/research/r3/shadow_ledger.jsonl",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="R3 canonical daily shadow feed")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--top-n", type=int, default=0,
                    help=("DEPRECATED for Lane A · retained for callers. "
                          "Lane A always covers the full eligible universe; "
                          "truncating it would reintroduce selection bias."))
    ap.add_argument("--root", default=str(_ROOT))
    ap.add_argument("--accumulate-outcomes", action="store_true", default=True,
                    help="fill any horizons that have closed (default on)")
    a = ap.parse_args()
    root = Path(a.root)

    markets = ["india", "usa"] if a.market == "both" else [a.market]
    for m in markets:
        print(json.dumps(run_daily_shadow(root, m, a.asof, a.top_n),
                         indent=2, default=str))

    if a.accumulate_outcomes:
        from backend.research.r3.outcomes import accumulate
        print(json.dumps(accumulate(root, a.asof), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

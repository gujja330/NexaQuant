"""
Sprint 7.7 · Headless engine drivers.

Programmatically executes Rec/Risk/Portfolio engines per historical asof
using the per-date feature snapshots Sprint 7.6 backfilled — WITHOUT
touching the current daily runners (which the live pipeline depends on).

Every engine class already accepts an `asof` parameter — this module wires
the historical inputs together and calls `.run(asof=D)` on each engine.

Anti-lookahead invariant (checked by lookahead_guard.py):
- All inputs to engine `.run(asof=D)` must be derivable from data with
  timestamp ≤ D. This module enforces that by:
    1. Feature snapshots loaded via `features/<market>/<D>.parquet`
       (Feature Store's asof-cutoff already bakes in the no-future rule)
    2. Model Factory predict_all(cutoff=D)
    3. Market Intelligence run(cutoff=D)
- Learning corpus outcomes computed ONLY for horizons that have closed
  by the current replay wall-clock date.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def _as_dict(obj) -> Any:
    if obj is None: return None
    if hasattr(obj, "__dataclass_fields__"):
        d = asdict(obj)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d
    if hasattr(obj, "value"):
        return obj.value
    return obj


def _sanitize(obj: Any) -> Any:
    """Recursively convert dataclasses/enums to JSON-safe primitives."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "value") and not hasattr(obj, "__dict__"):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return _sanitize(asdict(obj))
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return str(obj)


# ── Recommendation driver ──────────────────────────────────────────

def drive_recommendation(*, repo_root: Path, market: str, asof: date,
                            features_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Run Rec Engine v3 headlessly for a historical asof.

    Chain:
        Market Intel(cutoff=asof) → regime
        Model Factory.predict_all(features, cutoff=asof) → predictions
        Ensemble.top(predictions) → ensemble_top_rows
        Selected features (config-driven)
        Rec Engine.run(ensemble, features, selected_features, asof=asof) → batch

    Returns a dict payload identical to `recommendations_v3.json` shape (so
    append_snapshot_row lands it in recommendation_history.parquet with the
    same schema as the live daily runs).

    Returns None if any prerequisite is missing (fail-open — caller decides
    whether that's a hard error or a skip).
    """
    try:
        from backend.canonical import INDIA_PROFILE, USA_PROFILE
        from backend.market_intelligence.engine import MarketIntelligenceEngine
        from backend.model_factory.factory import ModelFactory
        from backend.model_factory.ensemble import ensemble_predict
        from backend.recommendation.engine import RecommendationEngine
        from backend.model_registry.registry import stamp
        from backend.feature_store import schema_fingerprint

        profile = INDIA_PROFILE if market == "india" else USA_PROFILE
        currency = "INR" if market == "india" else "USD"

        # 1) regime
        mi_engine = MarketIntelligenceEngine(repo_root, profile)
        mi_result = mi_engine.run(cutoff=asof)
        regime = _sanitize(getattr(mi_result, "regime", None)) or "neutral"
        if hasattr(regime, "value"):
            regime = regime.value
        regime = str(regime) if not isinstance(regime, str) else regime

        # 2) predictions via model factory
        mf = ModelFactory(repo_root=repo_root, market=market)
        try:
            predictions = mf.predict_all(features=features_df, cutoff=asof)
        except Exception:
            return None

        # 3) ensemble → DataFrame with ticker + ensemble_score + ensemble_confidence
        #    + n_models_scoring + per_model_score
        ens = ensemble_predict(predictions, weights=None, market=market, asof=asof)
        preds_df = ens.predictions
        if preds_df is None or preds_df.empty:
            return None

        ensemble_top_rows: List[Dict[str, Any]] = [
            {
                "ticker": str(r["ticker"]),
                "ensemble_score":      float(r["ensemble_score"]),
                "ensemble_confidence": float(r["ensemble_confidence"]),
                "n_models_scoring":    int(r["n_models_scoring"]),
                "per_model_score":     dict(r["per_model_score"]) if isinstance(r.get("per_model_score"), dict) else r.get("per_model_score"),
            }
            for _, r in preds_df.iterrows()
        ]

        # 4) selected features (config-owned)
        sel_path = repo_root / "reports" / "selected_features.json"
        selected_features: List[str] = []
        if sel_path.exists():
            try:
                sf = json.loads(sel_path.read_text(encoding="utf-8"))
                selected_features = sf.get("selected", []) or sf.get("features", []) or []
            except Exception:
                selected_features = []

        # 5) recommendation engine
        rec_engine = RecommendationEngine(
            repo_root=repo_root, market=market, regime=regime,
        )
        batch = rec_engine.run(
            ensemble_top_rows=ensemble_top_rows,
            features_df=features_df,
            selected_features=selected_features,
            asof=asof,
        )

        # 6) construct the JSON payload matching recommendations_v3.json shape
        model_stamp = stamp(repo_root, batch.engine)

        payload = {
            "engine": batch.engine, "version": getattr(batch, "version", "3.0.0"),
            "market": market,
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asof": asof.isoformat(),
            "currency": currency,
            "regime": regime,
            "n_tickers": batch.n_tickers,
            "distribution": {
                "STRONG_BUY":  batch.n_strong_buy, "BUY": batch.n_buy,
                "HOLD":        batch.n_hold,      "SELL": batch.n_sell,
                "STRONG_SELL": batch.n_strong_sell,
            },
            "n_disagreement_collapsed": batch.n_disagreement,
            "recommendations": [_sanitize(r) for r in batch.recommendations],
            "notes": batch.notes,
            "model_stamp": model_stamp,
            "replay": True,               # marker that this row was reconstructed
        }
        return payload

    except Exception as exc:
        return {"__error__": str(exc)}


# ── Risk driver ────────────────────────────────────────────────────

def drive_risk(*, repo_root: Path, market: str, asof: date,
                 features_df: pd.DataFrame,
                 recommendations_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        import yaml
        from backend.risk.engine import RiskEngine
        from backend.risk.types import RiskBudget
        from backend.model_registry.registry import stamp

        recs = recommendations_payload.get("recommendations", [])
        if not recs:
            return None

        # Load risk budget from configs (same as the live runner)
        budget_path = repo_root / "configs" / "risk_budget.yaml"
        m = {}
        if budget_path.exists():
            try:
                data = yaml.safe_load(budget_path.read_text(encoding="utf-8"))
                m = (data.get("market_defaults") or {}).get(market, {})
            except Exception:
                pass
        budget = RiskBudget(
            market=market,
            max_kelly_fraction=float(m.get("max_kelly_fraction", 0.25)),
            per_ticker_cap=float(m.get("per_ticker_cap", 0.06)),
            per_sector_cap=float(m.get("per_sector_cap", 0.25)),
            target_portfolio_vol=float(m.get("target_portfolio_vol", 0.15)),
            enable_shorts=bool(m.get("enable_shorts", False)),
            default_stop_loss_pct=float(m.get("default_stop_loss_pct", -0.08)),
            confidence_tier_mult=dict(m.get("confidence_tier_mult", {
                "STRONG_BUY": 1.0, "BUY": 0.6, "HOLD": 0.0,
                "SELL": -0.6, "STRONG_SELL": -1.0,
            })),
        )

        rk = RiskEngine(
            repo_root=repo_root, market=market, budget=budget,
            regime=recommendations_payload.get("regime", "neutral"),
        )
        sized, report = rk.run(recommendations=recs, features_df=features_df, asof=asof)

        payload = {
            "engine": rk.ENGINE_ID if hasattr(rk, "ENGINE_ID") else "aegis.risk.v1",
            "version": getattr(rk, "ENGINE_VERSION", "1.0.0"),
            "market": market,
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asof": asof.isoformat(),
            "regime": recommendations_payload.get("regime", "neutral"),
            **_sanitize(report),
            "model_stamp": stamp(repo_root, "aegis.risk.v1"),
            "replay": True,
        }
        # Attach sized positions for downstream portfolio
        payload["_sized_positions"] = [_sanitize(p) for p in sized]
        return payload
    except Exception as exc:
        return {"__error__": str(exc)}


# ── Portfolio driver ───────────────────────────────────────────────

def drive_portfolio(*, repo_root: Path, market: str, asof: date,
                       risk_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        import yaml
        from backend.portfolio.engine import PortfolioEngine
        from backend.model_registry.registry import stamp

        sized = risk_payload.get("_sized_positions", [])
        if not sized:
            return None

        # Load portfolio config
        cfg_path = repo_root / "configs" / "portfolio_config.yaml"
        cfg: Dict[str, Any] = {}
        if cfg_path.exists():
            try:
                data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                cfg = (data.get("market_defaults") or {}).get(market, {}) or data or {}
            except Exception:
                cfg = {}

        pe = PortfolioEngine(
            repo_root=repo_root, market=market,
            target_n_positions=int(cfg.get("target_n_positions", 15)),
            min_position_size=float(cfg.get("min_position_size", 0.02)),
            cash_reserve_min=float(cfg.get("cash_reserve_min", 0.05)),
            cash_reserve_stress=float(cfg.get("cash_reserve_stress", 0.20)),
            rebalance_threshold_bps=int(cfg.get("rebalance_threshold_bps", 50)),
            regime=risk_payload.get("regime", "neutral"),
        )
        snap, diff = pe.run(sized_positions=sized, asof=asof)

        payload = {
            "engine": pe.ENGINE_ID if hasattr(pe, "ENGINE_ID") else "aegis.portfolio.v1",
            "version": getattr(pe, "ENGINE_VERSION", "1.0.0"),
            "market": market,
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asof": asof.isoformat(),
            "currency": "INR" if market == "india" else "USD",
            "regime": risk_payload.get("regime", "neutral"),
            "snapshot": _sanitize(snap),
            "diff": _sanitize(diff),
            "model_stamp": stamp(repo_root, "aegis.portfolio.v1"),
            "replay": True,
        }
        return payload
    except Exception as exc:
        return {"__error__": str(exc)}


# ── Learning corpus outcomes ───────────────────────────────────────

def drive_learning_outcomes(*, repo_root: Path, market: str,
                                rec_payloads: List[Dict[str, Any]],
                                horizon_days: int = 20,
                                wall_clock: Optional[date] = None) -> Dict[str, Any]:
    """
    For every historical recommendation whose (asof + horizon_days) has already
    passed by `wall_clock`, compute the realized return from raw price parquets.

    Emits one learning-corpus row per (market, ticker, rec_asof).
    """
    from datetime import timedelta

    wall_clock = wall_clock or date.today()
    raw_dir = (repo_root / "data" / "raw" / "india") if market == "india" \
                else (repo_root / "usa" / "data" / "raw" / "us")

    outcomes: List[Dict[str, Any]] = []
    n_open = 0

    for payload in rec_payloads:
        try:
            rec_asof = datetime.strptime(payload["asof"], "%Y-%m-%d").date()
            close_asof = rec_asof + timedelta(days=horizon_days)
            if close_asof > wall_clock:
                n_open += 1
                continue

            for r in payload.get("recommendations", []):
                ticker = r.get("ticker")
                action = r.get("action")
                if not ticker or action in (None, "HOLD"):
                    continue

                # Find price parquet
                candidates = [
                    raw_dir / f"{ticker}_D1.parquet",
                    raw_dir / f"{ticker.replace('.','_')}_D1.parquet",
                ]
                pfile = next((c for c in candidates if c.exists()), None)
                if pfile is None:
                    continue

                df = pd.read_parquet(pfile)
                if "close" not in df.columns:
                    continue
                idx = df.index
                if hasattr(idx, "date"):
                    df = df.assign(_d=idx.date)
                elif "time" in df.columns:
                    df = df.assign(_d=pd.to_datetime(df["time"]).dt.date)
                else:
                    continue

                entry_row = df[df["_d"] == rec_asof]
                exit_row  = df[df["_d"] == close_asof]
                if entry_row.empty or exit_row.empty:
                    continue

                entry = float(entry_row.iloc[0]["close"])
                exit_ = float(exit_row.iloc[0]["close"])
                if entry <= 0: continue

                ret_pct = (exit_ - entry) / entry * 100.0
                if action in ("SELL", "STRONG_SELL"):
                    ret_pct = -ret_pct

                outcomes.append({
                    "market": market, "ticker": ticker,
                    "rec_asof": rec_asof.isoformat(),
                    "close_asof": close_asof.isoformat(),
                    "action": action,
                    "entry_price": entry, "exit_price": exit_,
                    "return_pct": round(ret_pct, 4),
                    "is_winner": bool(ret_pct > 0),
                    "horizon_days": horizon_days,
                    "confidence": r.get("regime_adjusted_confidence") or r.get("confidence"),
                    "score": r.get("ensemble_score") or r.get("score"),
                    "regime_at_entry": payload.get("regime"),
                    "replay": True,
                })
        except Exception:
            continue

    return {
        "n_outcomes": len(outcomes),
        "n_open_positions": n_open,
        "horizon_days": horizon_days,
        "outcomes": outcomes,
    }

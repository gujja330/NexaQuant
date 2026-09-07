"""AEGIS · R3 · CANONICAL SHADOW LEDGER SCHEMA · CEO 2026-09-07.

R3 Sprint 1, items 7-8. One canonical record replacing the two divergent
ledgers the R3-1 audit found (`backend/research/r3` had Signal only;
`backend/recommendation/runner3` had Signal + Risk; neither had Outcome,
Comparator or Attribution).

The absent Outcome block is why no Day-30/60/90 gate could ever produce
legitimate evidence, regardless of how many days accumulated.

    IDENTITY    position_id · market · ticker · asof · runner · shadow_only
    SIGNAL      score · probability · rank · model/feature/calibrator version
    RISK        entry · stop · target · sizing · horizon
    OUTCOME     fwd 5/10/20/60d · pnl · MAE · MFE       (filled forward)
    COMPARATOR  R2 score · R2 outcome · relative · rotation
    ATTRIBUTION top features · contributions · regime

FILL DISCIPLINE
---------------
A record is written ONCE at T0 with IDENTITY + SIGNAL + RISK + ATTRIBUTION
and an OUTCOME block whose horizons are all `PENDING`. The outcome
accumulator later fills a horizon only when that horizon has actually
closed on the trading calendar. Nothing is back-filled, nothing is
forward-filled, and an unavailable value is never fabricated:

    PENDING                 horizon has not closed yet
    NOT_AVAILABLE_AT_ASOF   horizon closed but the data was not knowable
    <number>                a real, measured outcome

This mirrors the AEGIS governance rule the audit cites: unavailable
historical information must not be fabricated or forward-filled.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

SCHEMA_VERSION = "aegis.r3.ledger.v2"

# Outcome horizons in TRADING days (not calendar days · see outcomes.py).
HORIZONS = (5, 10, 20, 60)

PENDING = "PENDING"
NOT_AVAILABLE = "NOT_AVAILABLE_AT_ASOF"


def features_hash(features: dict) -> str:
    s = json.dumps(features or {}, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def empty_outcome() -> dict:
    """OUTCOME block at T0 · every horizon explicitly PENDING.

    Explicit PENDING rather than a missing key, so a consumer can never
    read "absent" as "zero" · the failure mode that let a model-less
    engine publish `n_r2_trades_tagged: 0` as if it were a result.
    """
    out = {}
    for h in HORIZONS:
        out[f"fwd_{h}d_return_pct"] = PENDING
        out[f"fwd_{h}d_closed_on"] = PENDING
    out.update({
        "pnl_pct": PENDING,
        "mae_pct": PENDING,          # max adverse excursion
        "mfe_pct": PENDING,          # max favourable excursion
        "outcome_last_updated": None,
    })
    return out


def empty_comparator() -> dict:
    """COMPARATOR block · R2 side of the same name on the same day."""
    return {
        "r2_score": NOT_AVAILABLE,
        "r2_action": NOT_AVAILABLE,
        "r2_confidence": NOT_AVAILABLE,
        "r2_in_universe": NOT_AVAILABLE,
        "relative_return_pp": PENDING,
        "rotation_outcome": PENDING,
    }


def build_record(
    *,
    market: str,
    ticker: str,
    asof: str,
    # SIGNAL
    r3_score: Optional[float],
    r3_raw_p: Optional[float],
    r3_calibrated_p: Optional[float],
    rank: Optional[int],
    action: str,
    model_id: str,
    model_version: str,
    feature_version: str,
    calibrator_version: str,
    features: dict,
    # RISK
    entry_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    target_price: Optional[float] = None,
    horizon_days: Optional[int] = None,
    size_pct_simulated: Optional[float] = None,
    # ATTRIBUTION
    top_features: Optional[list] = None,
    regime: Optional[str] = None,
    # COMPARATOR (optional at T0)
    comparator: Optional[dict] = None,
) -> dict:
    """Assemble one canonical R3 shadow record.

    Identity is stamped by the caller via `identity.stamp_identity` so the
    R3 tree keeps a single place that mints Position IDs.
    """
    from datetime import datetime, timezone

    rec = {
        # ── meta
        "schema_version": SCHEMA_VERSION,
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # ── identity (runner / opportunity_id / shadow_only stamped after)
        "market": str(market).lower(),
        "ticker": str(ticker).upper().split(".", 1)[0],
        "asof": asof,
        # ── signal
        "signal": {
            "r3_score": _num(r3_score),
            "r3_raw_p": _num(r3_raw_p),
            "r3_calibrated_p": _num(r3_calibrated_p),
            "rank": rank,
            "action": str(action).upper(),
            "model_id": model_id,
            "model_version": model_version,
            "feature_version": feature_version,
            "calibrator_version": calibrator_version,
            "features_hash": features_hash(features),
            "n_features_used": len(features or {}),
        },
        # ── risk (simulation only · R3 opens nothing)
        "risk": {
            "entry_price": _num(entry_price),
            "stop_price": _num(stop_price),
            "target_price": _num(target_price),
            "horizon_days": horizon_days,
            "size_pct_simulated": _num(size_pct_simulated),
        },
        # ── outcome (filled forward by the accumulator)
        "outcome": empty_outcome(),
        # ── comparator
        "comparator": comparator or empty_comparator(),
        # ── attribution
        "attribution": {
            "top_features": top_features or [],
            "regime": regime or NOT_AVAILABLE,
        },
    }
    return rec


def _num(x) -> Optional[float]:
    try:
        return round(float(x), 6) if x is not None else None
    except (TypeError, ValueError):
        return None


def is_canonical(rec: dict) -> bool:
    """True when a record carries the full five-block schema."""
    return (rec.get("schema_version") == SCHEMA_VERSION
            and all(k in rec for k in
                    ("signal", "risk", "outcome", "comparator", "attribution")))


def migrate(rec: dict) -> dict:
    """Lift a legacy record (either old ledger) into the canonical shape.

    Legacy rows are preserved, not discarded · they are real observations.
    Fields the legacy schema never captured become PENDING/NOT_AVAILABLE
    rather than being invented.
    """
    if is_canonical(rec):
        return rec
    features_h = rec.get("features_hash") or features_hash(
        rec.get("features_used") or {})
    out = {
        "schema_version": SCHEMA_VERSION,
        "ts_utc": rec.get("ts_utc"),
        "market": str(rec.get("market", "")).lower(),
        "ticker": str(rec.get("ticker", "")).upper().split(".", 1)[0],
        "asof": rec.get("asof"),
        "runner": rec.get("runner", "R3"),
        "opportunity_id": rec.get("opportunity_id"),
        "shadow_only": True,
        "signal": {
            "r3_score": _num(rec.get("r3_score", rec.get("raw_score"))),
            "r3_raw_p": _num(rec.get("predicted_probability")),
            "r3_calibrated_p": _num(rec.get("r3_calibrated_p",
                                            rec.get("calibrated_confidence"))),
            "rank": rec.get("rank"),
            "action": str(rec.get("action") or NOT_AVAILABLE).upper(),
            "model_id": rec.get("model_id") or NOT_AVAILABLE,
            # Legacy rows predate versioned artifacts · saying so is the
            # honest answer, and it also makes them ineligible for any
            # evidence claim that requires reproducibility.
            "model_version": NOT_AVAILABLE,
            "feature_version": NOT_AVAILABLE,
            "calibrator_version": NOT_AVAILABLE,
            "features_hash": features_h,
            "n_features_used": len(rec.get("features_used") or {}),
        },
        "risk": {
            "entry_price": _num(rec.get("entry_price")),
            "stop_price": _num(rec.get("stop_pct")),
            "target_price": _num(rec.get("target_1_pct")),
            "horizon_days": rec.get("horizon_days"),
            "size_pct_simulated": None,
        },
        "outcome": empty_outcome(),
        "comparator": empty_comparator(),
        "attribution": {"top_features": [], "regime": NOT_AVAILABLE},
        "migrated_from_legacy": True,
    }
    return out

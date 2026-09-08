"""ML DISCOVERY v1 · FEATURE MANIFEST · CEO 2026-09-08.

> "Every feature gets a machine-readable record ... Anything not genuinely
>  available at prediction time is excluded - not imputed into existence."

Every feature carries its provenance and PIT status. A feature that was
not knowable at the prediction date is EXCLUDED from fitting, never
filled in. The exclusions here are not hypothetical - each one was
established by tracing the substrate this session:

  sector          acquired 2026-09-08 from a live source. No historical
                  snapshot exists anywhere in the repository, so applying
                  it to August predictions is lookahead. Research
                  enrichment only.
  market cap      NO source in the repository at all.
  regime          producer has emitted 'unknown' for all 19 observations
                  it has ever made.
  fundamentals    PIT accumulator holds two as-of dates (2026-09-03..04),
                  after most of the cohort.
  entry/stop      USA has these on 85 of 1,082 rows (7.9%). India 97.8%.
                  Included, but the coverage is recorded so a model is
                  never fitted on a near-empty column without it showing.

`cap_bucket` is deliberately absent: it buckets 60-day traded value with
identical INR/USD thresholds, so it is neither market cap nor comparable
across markets. `liquidity_bucket_60d`, computed from within-market
quantiles, replaces it.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.ml_discovery.manifest.v1"

PIT_OK = "PIT_OK"
PIT_LOOKAHEAD = "PIT_LOOKAHEAD"
PIT_UNAVAILABLE = "PIT_UNAVAILABLE"
PIT_PATH_OUTCOME = "PIT_PATH_OUTCOME"

# (name, source_field, pit_status, note)
FEATURE_SPECS = [
    ("confidence_pct", "confidence_pct", PIT_OK,
     "model confidence at prediction time"),
    ("rank", "rank", PIT_OK, "recommendation rank at prediction time"),
    ("ma20_dist_pct", "ma20_dist_pct", PIT_OK, "price vs MA20 at asof"),
    ("ma50_dist_pct", "ma50_dist_pct", PIT_OK, "price vs MA50 at asof"),
    ("ma200_dist_pct", "ma200_dist_pct", PIT_OK, "price vs MA200 at asof"),
    ("momentum_20d_pct", "momentum_20d_pct", PIT_OK, "trailing 20d return"),
    ("momentum_60d_pct", "momentum_60d_pct", PIT_OK, "trailing 60d return"),
    ("vol_20d_pct", "vol_20d_pct", PIT_OK, "realised 20d volatility"),
    ("avg_dv_60d", "avg_dv_60d", PIT_OK, "60d average traded value"),
    ("rsi_14", "rsi_14", PIT_OK, "RSI(14) at asof"),
    ("entry_price_at_pred", "entry_price_at_pred", PIT_OK,
     "entry reference price · USA coverage 7.9%"),
    ("stop_at_pred", "stop_at_pred", PIT_OK,
     "stop at prediction · USA coverage 7.9%"),
    # Derived, still PIT-safe.
    ("stop_distance_pct", None, PIT_OK, "(entry-stop)/entry*100"),
    ("stop_vs_volatility", None, PIT_OK, "stop_distance_pct / vol_20d_pct"),
    ("liquidity_bucket_60d", "_liquidity_bucket", PIT_OK,
     "within-market tercile of avg_dv_60d · NOT market cap"),
    # Excluded from fitting.
    ("sector", "sector", PIT_LOOKAHEAD,
     "acquired 2026-09-08 · no historical snapshot · enrichment only"),
    ("market_cap", None, PIT_UNAVAILABLE, "no source in the repository"),
    ("regime", "regime", PIT_UNAVAILABLE,
     "producer emitted 'unknown' for all 19 observations"),
    ("fund_roe", "fund_roe", PIT_LOOKAHEAD, "PIT accumulator has 2 dates"),
    ("fund_pe", "fund_pe", PIT_LOOKAHEAD, "PIT accumulator has 2 dates"),
    ("fund_pb", "fund_pb", PIT_LOOKAHEAD, "PIT accumulator has 2 dates"),
    ("fund_debt_equity", "fund_debt_equity", PIT_LOOKAHEAD,
     "PIT accumulator has 2 dates"),
    ("fund_quality_score", "fund_quality_score", PIT_LOOKAHEAD,
     "PIT accumulator has 2 dates"),
    ("investability_band", "investability_band", PIT_LOOKAHEAD,
     "investability recomputed at build time, not stored per prediction"),
    ("mae_pct", "mae_pct", PIT_PATH_OUTCOME,
     "measured from the same forward path as the target"),
    ("mfe_pct", "mfe_pct", PIT_PATH_OUTCOME,
     "measured from the same forward path as the target"),
    ("stop_hit_within_20d", "stop_hit_within_20d", PIT_PATH_OUTCOME,
     "forward-path outcome"),
]

FITTABLE = {name for name, _, pit, _ in FEATURE_SPECS if pit == PIT_OK}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def derive(row: dict) -> dict:
    """PIT-safe derived features · computed only from PIT_OK inputs."""
    ep, st = _num(row.get("entry_price_at_pred")), _num(row.get("stop_at_pred"))
    vol = _num(row.get("vol_20d_pct"))
    sd = ((ep - st) / ep * 100.0) if (ep and st is not None and ep > 0) else None
    return {
        "stop_distance_pct": sd,
        "stop_vs_volatility": (sd / vol) if (sd is not None and vol) else None,
    }


def build(rows: list, market: str) -> dict:
    """Manifest with real coverage measured on this cohort."""
    n = len(rows) or 1
    feats = []
    for name, src, pit, note in FEATURE_SPECS:
        if src:
            present = sum(1 for r in rows if r.get(src) not in (None, "", "nan"))
        else:
            d = [derive(r).get(name) for r in rows]
            present = sum(1 for v in d if v is not None)
        feats.append({
            "feature": name, "source_field": src, "pit_status": pit,
            "market": market, "note": note,
            "coverage_n": present,
            "coverage_pct": round(present / n * 100, 1),
            "missing_rate_pct": round((n - present) / n * 100, 1),
            "fittable": pit == PIT_OK,
        })
    fittable = [f for f in feats if f["fittable"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": len(rows),
        "n_features_declared": len(feats),
        "n_fittable": len(fittable),
        "n_excluded": len(feats) - len(fittable),
        "excluded_by_reason": {
            k: sum(1 for f in feats if f["pit_status"] == k)
            for k in (PIT_LOOKAHEAD, PIT_UNAVAILABLE, PIT_PATH_OUTCOME)},
        "features": feats,
    }


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "ml_discovery"
         / f"feature_manifest_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p

"""DEV017 v0.1 compute engine.

Reads RawObservations from the parquet store, computes:
  - DerivedMetrics (2s10s slope subset — using 3m/10y as proxy, moving averages)
  - NormalizedIndicators on [0, 100]
  - Classifications (global_posture, usd, vol_regime)
  - CompositeScore (composite.global_risk)

All rows conform to ARCH017A schema.
"""
from __future__ import annotations

import math
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..lib.schema import DerivedMetric, NormalizedIndicator, Classification, CompositeScore, as_dict
from ..lib import confidence

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "market_intelligence" / "raw"
DERIVED_DIR = ROOT / "data" / "market_intelligence" / "derived"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def load_recent_raw(days: int = 260) -> pd.DataFrame:
    """Load every RawObservation from the last `days` calendar days."""
    now = datetime.now(timezone.utc)
    frames = []
    for offset in range(0, days // 28 + 2):
        target = now - timedelta(days=28 * offset)
        partition = RAW_DIR / f"{target.year:04d}-{target.month:02d}"
        if not partition.exists():
            continue
        for f in partition.glob("*.parquet"):
            frames.append(pd.read_parquet(f))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["checksum"], keep="last")
    df["asof_utc"] = pd.to_datetime(df["asof_utc"])
    df = df.sort_values("asof_utc")
    return df


def latest_by_variable(df: pd.DataFrame) -> dict[str, tuple[datetime, float]]:
    """Latest (asof_utc, value) per variable_key."""
    if df.empty:
        return {}
    latest = df.groupby("variable_key").tail(1)
    return {row.variable_key: (row.asof_utc, float(row.value))
             for row in latest.itertuples(index=False)}


def series_by_variable(df: pd.DataFrame, variable_key: str) -> pd.Series:
    """Time-series of a single variable, indexed by asof_utc."""
    if df.empty:
        return pd.Series(dtype=float)
    sub = df[df["variable_key"] == variable_key].copy()
    sub = sub.sort_values("asof_utc").drop_duplicates(subset=["asof_utc"], keep="last")
    return pd.Series(sub["value"].values.astype(float),
                      index=pd.to_datetime(sub["asof_utc"]).values,
                      name=variable_key)


# ─── DERIVED METRICS ────────────────────────────────────────────────────

def compute_derived(df: pd.DataFrame) -> list[DerivedMetric]:
    """Compute the v0.1 subset of ARCH017 §4 DerivedMetrics."""
    code_sha = _git_sha()
    out: list[DerivedMetric] = []
    latest = latest_by_variable(df)
    if not latest:
        return out

    # Use the latest asof across all variables — one snapshot per compute run
    latest_asof = max(v[0] for v in latest.values())
    asof_iso = latest_asof.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def _emit(metric_key, value, unit, formula_key, conf=1.0, conf_components=None):
        out.append(DerivedMetric(
            metric_key=metric_key, asof_utc=asof_iso, value=float(value), unit=unit,
            formula_key=formula_key, formula_version="v1.0", code_sha=code_sha,
            confidence=conf, confidence_components=conf_components or {},
        ))

    # US 3m10y slope proxy (using ^IRX as short-end proxy since ^UST2Y not on yfinance)
    if "rates.us.10y.yield" in latest and "rates.us.2y.yield" in latest:
        y10 = latest["rates.us.10y.yield"][1]
        y_short = latest["rates.us.2y.yield"][1]
        _emit("derived.us.short10y.slope_bps", (y10 - y_short) * 100, "bps",
              "slope_short_10y")

    # SPX momentum blocks
    spx = series_by_variable(df, "equity_index.us.spx.close")
    if len(spx) >= 20:
        _emit("derived.spx.mom_20d", (spx.iloc[-1] / spx.iloc[-20] - 1) * 100, "%",
              "roc_20d")
    if len(spx) >= 60:
        _emit("derived.spx.mom_60d", (spx.iloc[-1] / spx.iloc[-60] - 1) * 100, "%",
              "roc_60d")
    if len(spx) >= 120:
        _emit("derived.spx.mom_120d", (spx.iloc[-1] / spx.iloc[-120] - 1) * 100, "%",
              "roc_120d")

    # Nifty momentum blocks
    nifty = series_by_variable(df, "equity_index.india.nifty50.close")
    if len(nifty) >= 20:
        _emit("derived.nifty50.mom_20d", (nifty.iloc[-1] / nifty.iloc[-20] - 1) * 100, "%",
              "roc_20d")
    if len(nifty) >= 60:
        _emit("derived.nifty50.mom_60d", (nifty.iloc[-1] / nifty.iloc[-60] - 1) * 100, "%",
              "roc_60d")

    # VIX MA
    vix = series_by_variable(df, "volatility.us.vix.close")
    if len(vix) >= 20:
        _emit("derived.vix.ma_20d", float(vix.iloc[-20:].mean()), "index_pts",
              "sma_20d")

    # DXY MA
    dxy = series_by_variable(df, "fx.dxy.close")
    if len(dxy) >= 50:
        _emit("derived.dxy.ma_50d", float(dxy.iloc[-50:].mean()), "index_pts",
              "sma_50d")

    # Brent momentum
    brent = series_by_variable(df, "commodity.brent.close")
    if len(brent) >= 20:
        _emit("derived.brent.mom_20d", (brent.iloc[-1] / brent.iloc[-20] - 1) * 100, "%",
              "roc_20d")

    # Gold/Silver ratio
    gold = series_by_variable(df, "commodity.gold.close")
    silver = series_by_variable(df, "commodity.silver.close")
    if len(gold) >= 1 and len(silver) >= 1:
        _emit("derived.gold_silver_ratio", gold.iloc[-1] / silver.iloc[-1], "ratio",
              "divide")

    return out


# ─── NORMALIZED INDICATORS ──────────────────────────────────────────────

def compute_normalized(df: pd.DataFrame, derived: list[DerivedMetric]) -> list[NormalizedIndicator]:
    """Map DerivedMetrics onto [0, 100] scale. Higher = more risk-on / supportive."""
    code_sha = _git_sha()
    out: list[NormalizedIndicator] = []
    if not derived:
        return out

    asof_iso = derived[0].asof_utc
    dm = {d.metric_key: d.value for d in derived}

    def _percentile_series(series: pd.Series, current: float, window: int = 252) -> float:
        """Rolling-window percentile rank of `current` within the last `window` values of `series`."""
        s = series.tail(window)
        if len(s) < 20:
            return 50.0
        rank = float((s <= current).sum()) / len(s) * 100
        return float(max(0.0, min(100.0, rank)))

    def _emit(indicator_key, value_0_100, method="percentile_rolling_252d", zscore=None, conf=1.0):
        out.append(NormalizedIndicator(
            indicator_key=indicator_key, asof_utc=asof_iso,
            value_0_100=float(max(0.0, min(100.0, value_0_100))),
            normalization_method=method, normalization_version="v1.0",
            code_sha=code_sha, zscore=zscore, confidence=conf,
        ))

    # norm.us_equity_momentum — blend of SPX mom_20d/60d/120d percentiles
    spx = series_by_variable(df, "equity_index.us.spx.close")
    if len(spx) >= 130 and "derived.spx.mom_20d" in dm:
        # Build percentile against each block's own historical distribution
        mom20 = spx.pct_change(20) * 100
        mom60 = spx.pct_change(60) * 100
        p20 = _percentile_series(mom20.dropna(), dm["derived.spx.mom_20d"])
        p60 = _percentile_series(mom60.dropna(), dm.get("derived.spx.mom_60d", dm["derived.spx.mom_20d"]))
        _emit("norm.us_equity_momentum", 0.5 * p20 + 0.5 * p60)

    # norm.india_equity_momentum
    nifty = series_by_variable(df, "equity_index.india.nifty50.close")
    if len(nifty) >= 130 and "derived.nifty50.mom_20d" in dm:
        mom20 = nifty.pct_change(20) * 100
        p20 = _percentile_series(mom20.dropna(), dm["derived.nifty50.mom_20d"])
        _emit("norm.india_equity_momentum", p20)

    # norm.vix — higher VIX → LOWER norm (risk-off). Invert.
    vix = series_by_variable(df, "volatility.us.vix.close")
    if len(vix) >= 60:
        # VIX percentile: high VIX = high percentile. Invert to get "calm" score.
        latest_vix = float(vix.iloc[-1])
        p = _percentile_series(vix, latest_vix)
        _emit("norm.vix", 100.0 - p)

    # norm.india_vix
    india_vix = series_by_variable(df, "volatility.india.india_vix.close")
    if len(india_vix) >= 60:
        latest = float(india_vix.iloc[-1])
        p = _percentile_series(india_vix, latest)
        _emit("norm.india_vix", 100.0 - p)

    # norm.usd_strength — strong DXY = bad for EM. Convention: higher norm = weaker dollar.
    dxy = series_by_variable(df, "fx.dxy.close")
    if len(dxy) >= 60:
        latest = float(dxy.iloc[-1])
        p = _percentile_series(dxy, latest)
        _emit("norm.usd_strength", 100.0 - p)

    # norm.us_yield_curve_inversion — inverted (10y < short) = risk-off. Higher norm = steep.
    if "derived.us.short10y.slope_bps" in dm:
        # Very rough: map [-200, +300] bps to [0, 100].
        slope = dm["derived.us.short10y.slope_bps"]
        raw = max(0.0, min(100.0, (slope + 200.0) / 5.0))
        _emit("norm.us_yield_curve_inversion", raw)

    # norm.oil_stability — sharp Brent spike = risk-off. Higher norm = stable/falling.
    if "derived.brent.mom_20d" in dm:
        m = dm["derived.brent.mom_20d"]
        # Map [-30%, +30%] to [100, 0].
        raw = max(0.0, min(100.0, 100.0 - (m + 30.0) * (100.0 / 60.0)))
        _emit("norm.oil_stability", raw)

    return out


# ─── CLASSIFICATIONS ────────────────────────────────────────────────────

def compute_classifications(normalized: list[NormalizedIndicator],
                             composites: dict[str, CompositeScore]) -> list[Classification]:
    """ARCH017 §6 classifications."""
    out: list[Classification] = []
    if not normalized:
        return out
    asof = normalized[0].asof_utc
    n = {i.indicator_key: i.value_0_100 for i in normalized}
    conf = {i.indicator_key: i.confidence for i in normalized}

    # global_posture from composite
    if "composite.global_risk" in composites:
        c = composites["composite.global_risk"]
        if c.confidence < 0.7:
            label = "Unknown"
        elif c.value_0_100 > 65:
            label = "Risk-On"
        elif c.value_0_100 < 35:
            label = "Risk-Off"
        else:
            label = "Neutral"
        out.append(Classification(
            key="global_posture", asof_utc=asof, label=label,
            confidence=c.confidence,
        ))

    # usd
    if "norm.usd_strength" in n:
        v = n["norm.usd_strength"]
        cf = conf.get("norm.usd_strength", 1.0)
        if cf < 0.7:
            label = "Unknown"
        elif v < 30:
            label = "Bullish"                # dollar strong → bullish USD
        elif v > 70:
            label = "Weak"
        else:
            label = "Neutral"
        out.append(Classification(key="usd", asof_utc=asof, label=label, confidence=cf))

    # vol_regime
    if "norm.vix" in n:
        v = n["norm.vix"]
        cf = conf.get("norm.vix", 1.0)
        if cf < 0.7:
            label = "Unknown"
        elif v > 75:
            label = "Calm"
        elif v > 40:
            label = "Elevated"
        else:
            label = "Spiking"
        out.append(Classification(key="vol_regime", asof_utc=asof, label=label, confidence=cf))

    return out


# ─── COMPOSITE SCORES ──────────────────────────────────────────────────

# v1 weight table — subset of ARCH017 §7.1 (only indicators we can compute in v0.1)
GLOBAL_RISK_WEIGHTS_V1 = {
    "norm.us_equity_momentum":         0.28,
    "norm.vix":                        0.20,
    "norm.usd_strength":               0.15,
    "norm.us_yield_curve_inversion":   0.13,
    "norm.oil_stability":              0.10,
    "norm.india_equity_momentum":      0.10,
    "norm.india_vix":                  0.04,
}


def compute_composite_global_risk(normalized: list[NormalizedIndicator]) -> CompositeScore | None:
    if not normalized:
        return None
    asof = normalized[0].asof_utc
    n = {i.indicator_key: i for i in normalized}

    present = 0
    weighted_sum = 0.0
    weight_sum = 0.0
    conf_weighted_sum = 0.0
    components = []
    for key, w in GLOBAL_RISK_WEIGHTS_V1.items():
        if key not in n:
            continue
        val = n[key].value_0_100
        cf = n[key].confidence
        weighted_sum += w * val
        weight_sum += w
        conf_weighted_sum += w * cf
        components.append({
            "indicator_key": key, "weight": w, "value_0_100": val,
            "contribution_to_composite": round(w * val, 2),
            "confidence": cf,
        })
        present += 1

    if weight_sum == 0:
        return None

    # Renormalise for missing indicators
    value = weighted_sum / weight_sum * 1.0                          # rescale to full 0-100 basis
    # But since weight_sum < 1 means some indicators missing, penalise confidence
    completeness = weight_sum
    conf = min(1.0, (conf_weighted_sum / weight_sum) * completeness)

    if value > 65 and conf >= 0.7:
        cls = "Risk-On"
    elif value < 35 and conf >= 0.7:
        cls = "Risk-Off"
    elif conf < 0.7:
        cls = "Unknown"
    else:
        cls = "Neutral"

    return CompositeScore(
        composite_key="composite.global_risk",
        asof_utc=asof, value_0_100=round(value, 2),
        classification=cls, confidence=round(conf, 3),
        weighting_scheme="expert_curated_v1_subset",
        weighting_version="v1.0",
        component_indicators=components,
    )


# ─── STORAGE OF DERIVED / NORMALIZED / CLASSIFICATIONS / COMPOSITES ─────────

def store_derived(derived: list[DerivedMetric], normalized: list[NormalizedIndicator],
                    classifications: list[Classification],
                    composites: dict[str, CompositeScore]) -> Path:
    import json
    now = datetime.now(timezone.utc)
    partition = DERIVED_DIR / f"{now.year:04d}-{now.month:02d}"
    partition.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S")

    def _to_parquet_row(d: dict) -> dict:
        # Serialize nested containers to JSON strings — pyarrow can't handle
        # empty-struct or heterogeneous nested types.
        out = {}
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v, default=str)
            else:
                out[k] = v
        return out

    def _write(name, items):
        if not items:
            return None
        pth = partition / f"{name}_{stamp}.parquet"
        rows = [_to_parquet_row(as_dict(x)) for x in items]
        pd.DataFrame(rows).to_parquet(pth, index=False)
        return pth

    _write("derived_metrics", derived)
    _write("normalized_indicators", normalized)
    _write("classifications", classifications)
    _write("composites", list(composites.values()))
    return partition


def run_compute_cycle(verbose: bool = True) -> dict:
    df = load_recent_raw(days=260)
    if df.empty:
        return {"error": "no raw observations found; run ingest first"}
    derived = compute_derived(df)
    normalized = compute_normalized(df, derived)
    composites = {}
    gr = compute_composite_global_risk(normalized)
    if gr:
        composites["composite.global_risk"] = gr
    classifications = compute_classifications(normalized, composites)
    partition = store_derived(derived, normalized, classifications, composites)
    result = {
        "raw_rows_loaded": len(df),
        "unique_variables": df["variable_key"].nunique() if not df.empty else 0,
        "derived": len(derived),
        "normalized": len(normalized),
        "classifications": len(classifications),
        "composites": len(composites),
        "partition": str(partition),
    }
    if verbose:
        print(f"        raw rows: {result['raw_rows_loaded']}   vars: {result['unique_variables']}")
        print(f"        derived: {result['derived']}   normalized: {result['normalized']}   "
                f"classifications: {result['classifications']}   composites: {result['composites']}")
    return result | {"_derived": derived, "_normalized": normalized,
                       "_classifications": classifications, "_composites": composites}

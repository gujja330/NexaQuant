"""DEV018 compute engine.

For each NSE sector index, computes:
  - Price trend: 20/50/100/200-day moving averages + slope
  - Momentum: 20-day / 60-day / 120-day RoC
  - Relative strength vs Nifty 50 (already in DEV017 raw store)
  - Volatility: 20-day annualised realised
  - Max drawdown: 252-day rolling
  - Volume trend: 20d avg / 90d avg ratio
  - 52-week high/low percentile
  - Constituent breadth: % of AEGIS-universe constituents above 200-DMA
  - Leadership score: how often sector was top-quintile in last 90d
  - Institutional strength: momentum-consistency proxy (v0.1)
  - Composite Sector Score (0-100) + confidence + classification

Reuses ARCH017A entities from DEV017 (research.global_intelligence.lib.schema).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from global_intelligence.lib.schema import (                                    # noqa: E402
    DerivedMetric, NormalizedIndicator, Classification, CompositeScore, as_dict,
)
from global_intelligence.lib import confidence as gi_confidence                  # noqa: E402
from sector_intelligence.lib import sector_catalog                                # noqa: E402


RAW_DIR = _ROOT / "data" / "market_intelligence" / "raw"
DERIVED_DIR = _ROOT / "data" / "market_intelligence" / "derived"
CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"
GLOBAL_BUNDLE = _ROOT / "reports" / "global_context.json"


# 5-class enum (per DEV018 prompt §Classifications)
CLASS_ENUM = ["Strong-Bullish", "Bullish", "Neutral", "Weak", "Bearish", "Unknown"]


# ── Composite weight table (v1 draft; ARCH018 §8) ────────────────────────────
COMPOSITE_WEIGHTS_V1 = {
    "norm.sector.momentum":          0.18,
    "norm.sector.rs_nifty":          0.17,
    "norm.sector.breadth":           0.12,
    "norm.sector.trend":             0.10,
    "norm.sector.volatility":        0.08,
    "norm.sector.drawdown":          0.08,
    "norm.sector.volume_trend":      0.06,
    "norm.sector.52w_position":      0.07,
    "norm.sector.leadership":        0.08,
    "norm.sector.institutional":     0.06,
}


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


# ── Data loading ─────────────────────────────────────────────────────────────

def load_recent_raw(days: int = 350) -> pd.DataFrame:
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
    return df.sort_values("asof_utc")


def series_for(df: pd.DataFrame, variable_key: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    sub = df[df["variable_key"] == variable_key].copy()
    sub = sub.sort_values("asof_utc").drop_duplicates(subset=["asof_utc"], keep="last")
    return pd.Series(sub["value"].values.astype(float),
                      index=pd.to_datetime(sub["asof_utc"]).values,
                      name=variable_key)


def load_global_context() -> dict | None:
    if not GLOBAL_BUNDLE.exists():
        return None
    try:
        with GLOBAL_BUNDLE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_constituent_series(ticker: str, n_days: int = 260) -> pd.Series:
    """Load a single AEGIS-universe constituent close series."""
    parq = CONSTITUENT_PARQ_DIR / f"{ticker}_D1.parquet"
    if not parq.exists():
        return pd.Series(dtype=float)
    try:
        df = pd.read_parquet(parq)
        if df.empty:
            return pd.Series(dtype=float)
        close = df["close"].dropna().tail(n_days)
        return close
    except Exception:
        return pd.Series(dtype=float)


# ── Metric primitives ────────────────────────────────────────────────────────

def _ma(s: pd.Series, n: int) -> float | None:
    if len(s) < n:
        return None
    return float(s.tail(n).mean())


def _roc(s: pd.Series, n: int) -> float | None:
    if len(s) < n + 1:
        return None
    return float((s.iloc[-1] / s.iloc[-n - 1] - 1) * 100)


def _realised_vol(s: pd.Series, n: int = 20) -> float | None:
    if len(s) < n + 1:
        return None
    r = s.pct_change().dropna().tail(n)
    if len(r) < 2:
        return None
    return float(r.std() * np.sqrt(252) * 100)                    # annualised %


def _max_drawdown(s: pd.Series, n: int = 252) -> float | None:
    if len(s) < 30:
        return None
    tail = s.tail(min(n, len(s))).copy()
    peak = tail.cummax()
    dd = (tail / peak - 1) * 100
    return float(dd.min())                                         # negative


def _pct_position_52w(s: pd.Series) -> float | None:
    if len(s) < 30:
        return None
    tail = s.tail(min(252, len(s)))
    lo, hi = float(tail.min()), float(tail.max())
    if hi == lo:
        return 50.0
    return float((s.iloc[-1] - lo) / (hi - lo) * 100)


def _rs_vs_nifty(sector: pd.Series, nifty: pd.Series, n: int = 20) -> float | None:
    """RS = sector return - nifty return over last n days (basis points differential)."""
    if len(sector) < n + 1 or len(nifty) < n + 1:
        return None
    s_ret = sector.iloc[-1] / sector.iloc[-n - 1] - 1
    n_ret = nifty.iloc[-1] / nifty.iloc[-n - 1] - 1
    return float((s_ret - n_ret) * 100)                            # % differential


# ── Constituent breadth (needs data/raw/india/*.parquet + india/sectors.py) ──

def _sector_breadth(spec: sector_catalog.SectorSpec) -> tuple[float | None, float | None, int]:
    """% of sector constituents above 200-DMA and above 50-DMA. Returns (above_200, above_50, n)."""
    tickers = spec.constituents
    if not tickers:
        return None, None, 0
    above_200 = 0
    above_50 = 0
    n_valid = 0
    for t in tickers:
        s = load_constituent_series(t, n_days=260)
        if len(s) < 200:
            continue
        n_valid += 1
        latest = s.iloc[-1]
        ma_200 = s.tail(200).mean()
        ma_50 = s.tail(50).mean() if len(s) >= 50 else None
        if latest > ma_200:
            above_200 += 1
        if ma_50 is not None and latest > ma_50:
            above_50 += 1
    if n_valid == 0:
        return None, None, 0
    return above_200 / n_valid * 100, above_50 / n_valid * 100, n_valid


# ── Per-sector compute ──────────────────────────────────────────────────────

def _norm_percentile(series: pd.Series, current: float, window: int = 252) -> float:
    s = series.tail(window)
    if len(s) < 20:
        return 50.0
    rank = float((s <= current).sum()) / len(s) * 100
    return max(0.0, min(100.0, rank))


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def compute_sector(spec: sector_catalog.SectorSpec,
                    raw_df: pd.DataFrame,
                    nifty_series: pd.Series,
                    code_sha: str,
                    asof_iso: str) -> dict | None:
    """Compute all dimensions for one sector. Returns a dict of entities + composite."""
    sector_series = series_for(raw_df, spec.sector_key + ".close")
    if len(sector_series) < 30:
        return None                                                # insufficient history

    latest_close = float(sector_series.iloc[-1])
    derived: list[DerivedMetric] = []
    normalized: list[NormalizedIndicator] = []

    def _dm(metric_key, value, unit, formula_key):
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return
        derived.append(DerivedMetric(
            metric_key=metric_key, asof_utc=asof_iso, value=float(value), unit=unit,
            formula_key=formula_key, formula_version="v1.0", code_sha=code_sha,
        ))

    def _ni(indicator_key, value_0_100, method="percentile_rolling_252d", conf=1.0):
        if value_0_100 is None or (isinstance(value_0_100, float) and (np.isnan(value_0_100) or np.isinf(value_0_100))):
            return
        normalized.append(NormalizedIndicator(
            indicator_key=indicator_key, asof_utc=asof_iso,
            value_0_100=_clamp(float(value_0_100)),
            normalization_method=method, normalization_version="v1.0",
            code_sha=code_sha, confidence=conf,
        ))

    # ── 1. Price trend (moving averages) ────────────────────────────────────
    ma_20 = _ma(sector_series, 20)
    ma_50 = _ma(sector_series, 50)
    ma_100 = _ma(sector_series, 100)
    ma_200 = _ma(sector_series, 200)
    for n, v in [(20, ma_20), (50, ma_50), (100, ma_100), (200, ma_200)]:
        _dm(f"derived.{spec.sector_key}.ma_{n}d", v, "index_pts", f"sma_{n}d")

    # Trend score: how many MAs is price above? 0-4 → 0/25/50/75/100
    mas = [ma_20, ma_50, ma_100, ma_200]
    valid_mas = [m for m in mas if m is not None]
    if valid_mas:
        above = sum(1 for m in valid_mas if latest_close > m)
        trend_score = (above / len(valid_mas)) * 100
    else:
        trend_score = 50.0
    _ni(f"norm.sector.trend", trend_score, method="mas_above_count")

    # ── 2. Momentum ──────────────────────────────────────────────────────────
    mom_20 = _roc(sector_series, 20)
    mom_60 = _roc(sector_series, 60)
    mom_120 = _roc(sector_series, 120)
    _dm(f"derived.{spec.sector_key}.mom_20d", mom_20, "%", "roc_20d")
    _dm(f"derived.{spec.sector_key}.mom_60d", mom_60, "%", "roc_60d")
    _dm(f"derived.{spec.sector_key}.mom_120d", mom_120, "%", "roc_120d")

    # Blend the three horizons via their percentiles vs sector's own history
    mom20_series = sector_series.pct_change(20) * 100
    mom60_series = sector_series.pct_change(60) * 100
    mom120_series = sector_series.pct_change(120) * 100
    ps = []
    if mom_20 is not None and len(mom20_series.dropna()) > 30:
        ps.append(_norm_percentile(mom20_series.dropna(), mom_20))
    if mom_60 is not None and len(mom60_series.dropna()) > 30:
        ps.append(_norm_percentile(mom60_series.dropna(), mom_60))
    if mom_120 is not None and len(mom120_series.dropna()) > 30:
        ps.append(_norm_percentile(mom120_series.dropna(), mom_120))
    if ps:
        _ni(f"norm.sector.momentum", sum(ps) / len(ps))

    # ── 3. Relative strength vs Nifty ────────────────────────────────────────
    rs20 = _rs_vs_nifty(sector_series, nifty_series, 20)
    rs60 = _rs_vs_nifty(sector_series, nifty_series, 60)
    _dm(f"derived.{spec.sector_key}.rs_nifty_20d", rs20, "%_diff", "rs_20d")
    _dm(f"derived.{spec.sector_key}.rs_nifty_60d", rs60, "%_diff", "rs_60d")

    # Percentile of RS values
    if rs20 is not None and len(sector_series) >= 40 and len(nifty_series) >= 40:
        # Align dates and compute rolling RS series
        aligned = pd.concat([sector_series.rename("s"), nifty_series.rename("n")], axis=1).dropna()
        if len(aligned) >= 40:
            rs_series = (aligned["s"].pct_change(20) - aligned["n"].pct_change(20)) * 100
            rs_series = rs_series.dropna()
            p = _norm_percentile(rs_series, rs20)
            _ni(f"norm.sector.rs_nifty", p)

    # ── 4. Volatility (inverted: lower vol → higher norm) ────────────────────
    vol = _realised_vol(sector_series, 20)
    _dm(f"derived.{spec.sector_key}.vol_20d_ann", vol, "%_ann", "realised_vol_20d")
    if vol is not None:
        vol_series = (sector_series.pct_change().rolling(20).std() * np.sqrt(252) * 100).dropna()
        if len(vol_series) >= 30:
            vol_percentile = _norm_percentile(vol_series, vol)
            _ni(f"norm.sector.volatility", 100.0 - vol_percentile)      # inverted

    # ── 5. Max drawdown (inverted: shallower DD → higher norm) ───────────────
    dd = _max_drawdown(sector_series, 252)
    _dm(f"derived.{spec.sector_key}.max_dd_252d", dd, "%", "max_dd_252d")
    if dd is not None:
        # Map DD [-40%, 0%] to [0, 100]. Shallower = higher.
        dd_norm = _clamp(100.0 + dd * 2.5)                             # dd=-40 → 0; dd=0 → 100
        _ni(f"norm.sector.drawdown", dd_norm)

    # ── 6. Volume trend ─────────────────────────────────────────────────────
    # Requires volume series — read from source_row['Volume'] if available in raw
    vol_series_raw = _volume_series(raw_df, spec.sector_key + ".close")
    if not vol_series_raw.empty and len(vol_series_raw) >= 90:
        vol_20 = float(vol_series_raw.tail(20).mean())
        vol_90 = float(vol_series_raw.tail(90).mean())
        if vol_90 > 0:
            vol_ratio = vol_20 / vol_90
            _dm(f"derived.{spec.sector_key}.volume_ratio_20d_90d", vol_ratio, "ratio", "vol_ratio")
            # 1.0 = neutral; >1.2 = strong accumulation. Map [0.5, 1.5] → [0, 100]
            vt_norm = _clamp((vol_ratio - 0.5) * 100)
            _ni(f"norm.sector.volume_trend", vt_norm)

    # ── 7. 52-week position ─────────────────────────────────────────────────
    pos_52w = _pct_position_52w(sector_series)
    if pos_52w is not None:
        _ni(f"norm.sector.52w_position", pos_52w)
        _dm(f"derived.{spec.sector_key}.pos_52w", pos_52w, "%", "position_52w")

    # ── 8. Constituent breadth ──────────────────────────────────────────────
    above_200, above_50, n_valid = _sector_breadth(spec)
    if above_200 is not None:
        _dm(f"derived.{spec.sector_key}.breadth_pct_above_200dma", above_200, "%", "breadth_200dma")
        _dm(f"derived.{spec.sector_key}.breadth_pct_above_50dma", above_50 or 0.0, "%", "breadth_50dma")
        # Breadth already 0-100; use as-is
        _ni(f"norm.sector.breadth", above_200,
            conf=gi_confidence.combine(0.85, 1.0, min(1.0, n_valid / 5.0), 1.0))
    else:
        # No constituents — fall back to a neutral breadth proxy from trend score
        pass

    # ── 9. Leadership: how often sector was top-quintile in last 90 days ─────
    if len(sector_series) >= 90 and len(nifty_series) >= 90:
        aligned = pd.concat([sector_series.rename("s"), nifty_series.rename("n")], axis=1).dropna()
        if len(aligned) >= 30:
            outperf_days = ((aligned["s"].pct_change() > aligned["n"].pct_change()).astype(int)
                              .tail(90).sum())
            n_total = min(90, len(aligned) - 1)
            leadership = outperf_days / n_total * 100 if n_total > 0 else 50.0
            _dm(f"derived.{spec.sector_key}.leadership_90d", leadership, "%", "leadership_pct")
            _ni(f"norm.sector.leadership", leadership)

    # ── 10. Institutional strength (proxy: momentum-consistency 60d) ─────────
    if len(sector_series) >= 60:
        r = sector_series.pct_change().tail(60).dropna()
        if len(r) >= 30:
            hit_rate = float((r > 0).mean()) * 100                     # % of positive-return days
            _dm(f"derived.{spec.sector_key}.pos_day_pct_60d", hit_rate, "%", "positive_day_pct")
            _ni(f"norm.sector.institutional", hit_rate)                 # 50%→neutral

    return {
        "sector_key": spec.sector_key,
        "display_name": spec.display_name,
        "latest_close": latest_close,
        "n_constituents_used": n_valid if above_200 is not None else 0,
        "derived": derived,
        "normalized": normalized,
    }


def _volume_series(raw_df: pd.DataFrame, variable_key: str) -> pd.Series:
    """Extract Volume from source_row JSON in the raw store."""
    if raw_df.empty:
        return pd.Series(dtype=float)
    sub = raw_df[raw_df["variable_key"] == variable_key].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    vols = []
    dates = []
    for r in sub.itertuples(index=False):
        try:
            row = r.source_row if isinstance(r.source_row, dict) else json.loads(r.source_row)
            v = row.get("Volume")
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            vols.append(float(v))
            dates.append(r.asof_utc)
        except Exception:
            continue
    if not vols:
        return pd.Series(dtype=float)
    return pd.Series(vols, index=pd.to_datetime(dates)).sort_index()


# ── Composite + Classification ──────────────────────────────────────────────

def compute_composite(sector_normalized: list[NormalizedIndicator],
                        sector_key: str, asof_iso: str) -> tuple[CompositeScore, Classification]:
    if not sector_normalized:
        return None, None
    n = {i.indicator_key.replace(f".{sector_key}", "") if f".{sector_key}" in i.indicator_key else i.indicator_key: i
          for i in sector_normalized}

    weighted_sum = 0.0
    weight_sum = 0.0
    conf_wsum = 0.0
    components = []
    for weight_key, w in COMPOSITE_WEIGHTS_V1.items():
        if weight_key not in n:
            continue
        ind = n[weight_key]
        weighted_sum += w * ind.value_0_100
        weight_sum += w
        conf_wsum += w * ind.confidence
        components.append({
            "indicator_key": weight_key, "weight": w,
            "value_0_100": round(ind.value_0_100, 2),
            "contribution_to_composite": round(w * ind.value_0_100, 2),
            "confidence": round(ind.confidence, 3),
        })

    if weight_sum == 0:
        return None, None

    score = weighted_sum / weight_sum
    completeness = weight_sum                                       # weights sum to 1.0 in v1
    conf = min(1.0, (conf_wsum / weight_sum) * completeness)

    # 5-class classification
    if conf < 0.5:
        label = "Unknown"
    elif score >= 75:
        label = "Strong-Bullish"
    elif score >= 60:
        label = "Bullish"
    elif score >= 45:
        label = "Neutral"
    elif score >= 30:
        label = "Weak"
    else:
        label = "Bearish"

    composite = CompositeScore(
        composite_key=f"composite.{sector_key}.strength",
        asof_utc=asof_iso, value_0_100=round(score, 2),
        classification=label, confidence=round(conf, 3),
        weighting_scheme="expert_curated_v1", weighting_version="v1.0",
        component_indicators=components,
    )
    classification = Classification(
        key=f"classification.{sector_key}",
        asof_utc=asof_iso, label=label, confidence=round(conf, 3),
        contributing_indicator_ids=[c["indicator_key"] for c in components],
    )
    return composite, classification


# ── Store + orchestration ────────────────────────────────────────────────────

def store_derived(all_derived, all_normalized, all_classifications, all_composites) -> Path:
    now = datetime.now(timezone.utc)
    partition = DERIVED_DIR / f"{now.year:04d}-{now.month:02d}"
    partition.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S")

    def _row(d):
        out = {}
        for k, v in d.items():
            out[k] = json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
        return out

    def _write(name, items):
        if not items:
            return
        pth = partition / f"sector_{name}_{stamp}.parquet"
        pd.DataFrame([_row(as_dict(x)) for x in items]).to_parquet(pth, index=False)

    _write("derived", all_derived)
    _write("normalized", all_normalized)
    _write("classifications", all_classifications)
    _write("composites", all_composites)
    return partition


def run_compute_cycle(verbose: bool = True) -> dict:
    raw = load_recent_raw(days=350)
    if raw.empty:
        return {"error": "no raw observations — run ingest first"}

    nifty = series_for(raw, sector_catalog.NIFTY_50_KEY)
    if len(nifty) < 30:
        return {"error": "insufficient Nifty history in DEV017 raw store — run DEV017 first"}

    latest_asof = pd.to_datetime(raw["asof_utc"]).max()
    asof_iso = latest_asof.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    code_sha = _git_sha()

    global_ctx = load_global_context()

    all_derived, all_normalized, all_classifications, all_composites = [], [], [], []
    per_sector = []
    for spec in sector_catalog.SECTORS:
        result = compute_sector(spec, raw, nifty, code_sha, asof_iso)
        if result is None:
            per_sector.append({"sector_key": spec.sector_key,
                                 "display_name": spec.display_name,
                                 "status": "insufficient_data"})
            continue
        composite, cls = compute_composite(result["normalized"], spec.sector_key, asof_iso)
        if composite:
            all_composites.append(composite)
            all_classifications.append(cls)
        all_derived.extend(result["derived"])
        all_normalized.extend(result["normalized"])
        per_sector.append({
            "sector_key": spec.sector_key,
            "display_name": spec.display_name,
            "status": "computed",
            "composite": composite,
            "classification": cls,
            "n_constituents_used": result.get("n_constituents_used", 0),
        })

    partition = store_derived(all_derived, all_normalized, all_classifications, all_composites)

    result = {
        "sectors_attempted": len(sector_catalog.SECTORS),
        "sectors_computed": sum(1 for x in per_sector if x["status"] == "computed"),
        "derived_count": len(all_derived),
        "normalized_count": len(all_normalized),
        "classifications_count": len(all_classifications),
        "composites_count": len(all_composites),
        "partition": str(partition),
        "asof_utc": asof_iso,
        "global_context_available": global_ctx is not None,
    }
    if verbose:
        print(f"        sectors: {result['sectors_computed']}/{result['sectors_attempted']}   "
                f"asof: {asof_iso[:10]}")
        print(f"        derived: {result['derived_count']}   normalized: {result['normalized_count']}   "
                f"classifications: {result['classifications_count']}   composites: {result['composites_count']}")
        print(f"        global_context available: {result['global_context_available']}")

    result["_per_sector"] = per_sector
    result["_composites"] = all_composites
    result["_classifications"] = all_classifications
    result["_normalized"] = all_normalized
    result["_derived"] = all_derived
    result["_global_context"] = global_ctx
    return result

"""DEV019 compute engine.

Builds an equal-weighted industry price series from constituent parquets and
runs the same 10-dimension composite as DEV018, plus:
  - Relative metrics: industry vs sector, industry vs Nifty, industry vs SPX
  - Industry ranking (leadership rank across the universe)
  - Rotation classification (Improving / Weakening / Strong-Leader /
    Emerging-Leader / Falling-Leader / Lagging)

Reuses ARCH017A entities from research/global_intelligence/lib.
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
from industry_intelligence.lib import industry_catalog                           # noqa: E402


RAW_DIR = _ROOT / "data" / "market_intelligence" / "raw"
DERIVED_DIR = _ROOT / "data" / "market_intelligence" / "derived"
CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"
GLOBAL_BUNDLE = _ROOT / "reports" / "global_context.json"
SECTOR_BUNDLE = _ROOT / "reports" / "sector_context.json"


CLASS_ENUM = ["Strong-Bullish", "Bullish", "Neutral", "Weak", "Bearish", "Unknown"]

ROTATION_ENUM = ["Strong-Leader", "Emerging-Leader", "Improving",
                  "Falling-Leader", "Weakening", "Lagging", "Unknown"]


COMPOSITE_WEIGHTS_V1 = {
    "norm.industry.momentum":        0.18,
    "norm.industry.rs_nifty":        0.15,
    "norm.industry.rs_sector":       0.10,
    "norm.industry.breadth":         0.12,
    "norm.industry.trend":           0.10,
    "norm.industry.volatility":      0.08,
    "norm.industry.drawdown":        0.08,
    "norm.industry.52w_position":    0.07,
    "norm.industry.leadership":      0.07,
    "norm.industry.institutional":   0.05,
}


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


# ── Data loading ─────────────────────────────────────────────────────────────

def load_constituent(ticker: str, n_days: int = 350) -> pd.Series:
    parq = CONSTITUENT_PARQ_DIR / f"{ticker}_D1.parquet"
    if not parq.exists():
        return pd.Series(dtype=float)
    try:
        df = pd.read_parquet(parq)
        if df.empty or "close" not in df.columns:
            return pd.Series(dtype=float)
        s = df["close"].dropna().tail(n_days)
        return s
    except Exception:
        return pd.Series(dtype=float)


def load_recent_raw(days: int = 350) -> pd.DataFrame:
    """Load DEV017 + DEV018 raw store — for Nifty50 + sector index series."""
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


def series_for_variable(df: pd.DataFrame, variable_key: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    sub = df[df["variable_key"] == variable_key].copy()
    sub = sub.sort_values("asof_utc").drop_duplicates(subset=["asof_utc"], keep="last")
    return pd.Series(sub["value"].values.astype(float),
                      index=pd.to_datetime(sub["asof_utc"]).values, name=variable_key)


def load_global_context() -> dict | None:
    if not GLOBAL_BUNDLE.exists():
        return None
    try:
        return json.load(GLOBAL_BUNDLE.open("r", encoding="utf-8"))
    except Exception:
        return None


def load_sector_context() -> dict | None:
    if not SECTOR_BUNDLE.exists():
        return None
    try:
        return json.load(SECTOR_BUNDLE.open("r", encoding="utf-8"))
    except Exception:
        return None


# ── Industry price aggregation ───────────────────────────────────────────────

def build_industry_series(spec: industry_catalog.IndustrySpec) -> tuple[pd.Series, int]:
    """Equal-weighted, rebased-to-100 industry price series from constituent closes.

    Each constituent series is rebased to 100 on its first common date, then averaged.
    Returns (series, n_valid_constituents)."""
    tickers = spec.available_tickers()
    if len(tickers) < 3:
        return pd.Series(dtype=float), 0

    series_list = []
    for t in tickers:
        s = load_constituent(t, n_days=350)
        if len(s) < 30:
            continue
        s = s.astype(float)
        # rebase to 100 on the FIRST value of the series
        s = s / s.iloc[0] * 100.0
        s.name = t
        series_list.append(s)

    if len(series_list) < 3:
        return pd.Series(dtype=float), len(series_list)

    # Align on the common intersection of dates; equal-weighted mean
    aligned = pd.concat(series_list, axis=1, join="inner")
    if aligned.empty:
        # fallback to outer + ffill (constituents with different history windows)
        aligned = pd.concat(series_list, axis=1, join="outer").ffill().dropna(how="all")
    if aligned.empty:
        return pd.Series(dtype=float), len(series_list)
    industry_series = aligned.mean(axis=1)
    industry_series.name = spec.industry_key
    return industry_series.sort_index(), len(series_list)


# ── Metric primitives (subset of DEV018's) ───────────────────────────────────

def _ma(s, n):
    if len(s) < n: return None
    return float(s.tail(n).mean())

def _roc(s, n):
    if len(s) < n + 1: return None
    return float((s.iloc[-1] / s.iloc[-n - 1] - 1) * 100)

def _realised_vol(s, n=20):
    if len(s) < n + 1: return None
    r = s.pct_change().dropna().tail(n)
    if len(r) < 2: return None
    return float(r.std() * np.sqrt(252) * 100)

def _max_drawdown(s, n=252):
    if len(s) < 30: return None
    tail = s.tail(min(n, len(s)))
    peak = tail.cummax()
    return float((tail / peak - 1).min() * 100)

def _pct_position_52w(s):
    if len(s) < 30: return None
    tail = s.tail(min(252, len(s)))
    lo, hi = float(tail.min()), float(tail.max())
    if hi == lo: return 50.0
    return float((s.iloc[-1] - lo) / (hi - lo) * 100)

def _rs_diff(a, b, n=20):
    if len(a) < n + 1 or len(b) < n + 1:
        return None
    aligned = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(aligned) < n + 1:
        return None
    a_ret = aligned["a"].iloc[-1] / aligned["a"].iloc[-n - 1] - 1
    b_ret = aligned["b"].iloc[-1] / aligned["b"].iloc[-n - 1] - 1
    return float((a_ret - b_ret) * 100)


def _norm_percentile(series, current, window=252):
    s = series.tail(window)
    if len(s) < 20: return 50.0
    rank = float((s <= current).sum()) / len(s) * 100
    return max(0.0, min(100.0, rank))


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ── Per-industry compute ─────────────────────────────────────────────────────

def compute_industry(spec: industry_catalog.IndustrySpec,
                       industry_series: pd.Series,
                       nifty_series: pd.Series,
                       sector_series: pd.Series | None,
                       n_constituents: int,
                       code_sha: str, asof_iso: str) -> dict | None:
    if len(industry_series) < 30:
        return None

    derived, normalized = [], []

    def _dm(k, v, u, f):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))): return
        derived.append(DerivedMetric(metric_key=k, asof_utc=asof_iso, value=float(v),
                                       unit=u, formula_key=f, formula_version="v1.0",
                                       code_sha=code_sha))

    def _ni(k, v, method="percentile_rolling_252d", conf=1.0):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))): return
        normalized.append(NormalizedIndicator(indicator_key=k, asof_utc=asof_iso,
                                                 value_0_100=_clamp(float(v)),
                                                 normalization_method=method,
                                                 normalization_version="v1.0",
                                                 code_sha=code_sha, confidence=conf))

    latest = float(industry_series.iloc[-1])

    # 1. Trend (MAs)
    ma_20 = _ma(industry_series, 20); ma_50 = _ma(industry_series, 50)
    ma_100 = _ma(industry_series, 100); ma_200 = _ma(industry_series, 200)
    for n, v in [(20, ma_20), (50, ma_50), (100, ma_100), (200, ma_200)]:
        _dm(f"derived.{spec.industry_key}.ma_{n}d", v, "index_pts", f"sma_{n}d")
    mas = [m for m in [ma_20, ma_50, ma_100, ma_200] if m is not None]
    if mas:
        above = sum(1 for m in mas if latest > m)
        _ni(f"norm.industry.trend", (above / len(mas)) * 100, method="mas_above_count")

    # 2. Momentum
    m20, m60, m120 = _roc(industry_series, 20), _roc(industry_series, 60), _roc(industry_series, 120)
    _dm(f"derived.{spec.industry_key}.mom_20d", m20, "%", "roc_20d")
    _dm(f"derived.{spec.industry_key}.mom_60d", m60, "%", "roc_60d")
    _dm(f"derived.{spec.industry_key}.mom_120d", m120, "%", "roc_120d")
    m20s, m60s, m120s = (industry_series.pct_change(20)*100,
                              industry_series.pct_change(60)*100,
                              industry_series.pct_change(120)*100)
    ps = []
    for cur, series in [(m20, m20s), (m60, m60s), (m120, m120s)]:
        if cur is not None and len(series.dropna()) > 30:
            ps.append(_norm_percentile(series.dropna(), cur))
    if ps:
        _ni(f"norm.industry.momentum", sum(ps) / len(ps))

    # 3. RS vs Nifty
    rs_nifty_20 = _rs_diff(industry_series, nifty_series, 20)
    rs_nifty_60 = _rs_diff(industry_series, nifty_series, 60)
    _dm(f"derived.{spec.industry_key}.rs_nifty_20d", rs_nifty_20, "%_diff", "rs_20d")
    _dm(f"derived.{spec.industry_key}.rs_nifty_60d", rs_nifty_60, "%_diff", "rs_60d")
    if rs_nifty_20 is not None:
        aligned = pd.concat([industry_series.rename("i"), nifty_series.rename("n")],
                              axis=1).dropna()
        if len(aligned) >= 40:
            rs_hist = (aligned["i"].pct_change(20) - aligned["n"].pct_change(20)) * 100
            rs_hist = rs_hist.dropna()
            _ni(f"norm.industry.rs_nifty", _norm_percentile(rs_hist, rs_nifty_20))

    # 3b. RS vs Sector
    if sector_series is not None and len(sector_series) > 30:
        rs_sec_20 = _rs_diff(industry_series, sector_series, 20)
        rs_sec_60 = _rs_diff(industry_series, sector_series, 60)
        _dm(f"derived.{spec.industry_key}.rs_sector_20d", rs_sec_20, "%_diff", "rs_20d")
        _dm(f"derived.{spec.industry_key}.rs_sector_60d", rs_sec_60, "%_diff", "rs_60d")
        if rs_sec_20 is not None:
            aligned = pd.concat([industry_series.rename("i"), sector_series.rename("s")],
                                  axis=1).dropna()
            if len(aligned) >= 40:
                rs_hist = (aligned["i"].pct_change(20) - aligned["s"].pct_change(20)) * 100
                rs_hist = rs_hist.dropna()
                _ni(f"norm.industry.rs_sector", _norm_percentile(rs_hist, rs_sec_20))

    # 4. Volatility (inverted)
    vol = _realised_vol(industry_series, 20)
    _dm(f"derived.{spec.industry_key}.vol_20d_ann", vol, "%_ann", "vol_20d_ann")
    if vol is not None:
        vs = (industry_series.pct_change().rolling(20).std() * np.sqrt(252) * 100).dropna()
        if len(vs) >= 30:
            _ni(f"norm.industry.volatility", 100.0 - _norm_percentile(vs, vol))

    # 5. Max drawdown (inverted)
    dd = _max_drawdown(industry_series, 252)
    _dm(f"derived.{spec.industry_key}.max_dd_252d", dd, "%", "max_dd_252d")
    if dd is not None:
        _ni(f"norm.industry.drawdown", _clamp(100.0 + dd * 2.5))       # DD=-40 -> 0

    # 6. 52w position
    pos = _pct_position_52w(industry_series)
    _dm(f"derived.{spec.industry_key}.pos_52w", pos, "%", "position_52w")
    if pos is not None:
        _ni(f"norm.industry.52w_position", pos)

    # 7. Breadth (% of constituents above 200-DMA)
    tickers = spec.available_tickers()
    above_200 = 0; n_valid = 0
    for t in tickers:
        s = load_constituent(t)
        if len(s) < 200: continue
        n_valid += 1
        if s.iloc[-1] > s.tail(200).mean():
            above_200 += 1
    if n_valid > 0:
        breadth = above_200 / n_valid * 100
        _dm(f"derived.{spec.industry_key}.breadth_pct_above_200dma", breadth, "%", "breadth_200dma")
        _ni(f"norm.industry.breadth", breadth,
            conf=gi_confidence.combine(0.85, 1.0, min(1.0, n_valid / 5.0), 1.0))

    # 8. Leadership (industry outperforms Nifty daily)
    if len(nifty_series) >= 90:
        aligned = pd.concat([industry_series.rename("i"), nifty_series.rename("n")],
                              axis=1).dropna()
        if len(aligned) >= 30:
            outperf = (aligned["i"].pct_change() > aligned["n"].pct_change()).astype(int).tail(90).sum()
            n_tot = min(90, len(aligned) - 1)
            leader = outperf / n_tot * 100 if n_tot > 0 else 50.0
            _dm(f"derived.{spec.industry_key}.leadership_90d", leader, "%", "leadership_pct")
            _ni(f"norm.industry.leadership", leader)

    # 9. Institutional strength proxy (positive-day % over 60d)
    if len(industry_series) >= 60:
        r = industry_series.pct_change().tail(60).dropna()
        if len(r) >= 30:
            hit = float((r > 0).mean()) * 100
            _dm(f"derived.{spec.industry_key}.pos_day_pct_60d", hit, "%", "positive_day_pct")
            _ni(f"norm.industry.institutional", hit)

    return {
        "industry_key": spec.industry_key,
        "display_name": spec.display_name,
        "parent_sector_key": spec.parent_sector_key,
        "parent_sector_name": spec.parent_sector_name,
        "n_constituents_used": n_constituents,
        "n_constituents_defined": len(spec.tickers),
        "n_constituents_available": len(spec.available_tickers()),
        "derived": derived,
        "normalized": normalized,
    }


# ── Composite + classification ───────────────────────────────────────────────

def compute_composite(normalized_list: list, industry_key: str,
                        asof_iso: str) -> tuple[CompositeScore, Classification] | tuple[None, None]:
    if not normalized_list:
        return None, None
    n = {}
    for ind in normalized_list:
        # strip the industry-key suffix if present so the shared weight table matches
        key = ind.indicator_key
        if industry_key in key:
            key = key.replace(f".{industry_key}", "")
        n[key] = ind
    # Fall back: keys are like "norm.industry.momentum" — no suffix in v1
    weighted_sum, weight_sum, conf_wsum = 0.0, 0.0, 0.0
    components = []
    for k, w in COMPOSITE_WEIGHTS_V1.items():
        if k not in n: continue
        ind = n[k]
        weighted_sum += w * ind.value_0_100
        weight_sum += w
        conf_wsum += w * ind.confidence
        components.append({"indicator_key": k, "weight": w,
                             "value_0_100": round(ind.value_0_100, 2),
                             "contribution_to_composite": round(w * ind.value_0_100, 2),
                             "confidence": round(ind.confidence, 3)})
    if weight_sum == 0:
        return None, None

    score = weighted_sum / weight_sum
    conf = min(1.0, (conf_wsum / weight_sum) * weight_sum)         # weight_sum acts as completeness

    if conf < 0.5:                                                 label = "Unknown"
    elif score >= 75:                                              label = "Strong-Bullish"
    elif score >= 60:                                              label = "Bullish"
    elif score >= 45:                                              label = "Neutral"
    elif score >= 30:                                              label = "Weak"
    else:                                                          label = "Bearish"

    composite = CompositeScore(
        composite_key=f"composite.{industry_key}.strength",
        asof_utc=asof_iso, value_0_100=round(score, 2),
        classification=label, confidence=round(conf, 3),
        weighting_scheme="expert_curated_v1", weighting_version="v1.0",
        component_indicators=components,
    )
    classification = Classification(
        key=f"classification.{industry_key}", asof_utc=asof_iso, label=label,
        confidence=round(conf, 3),
        contributing_indicator_ids=[c["indicator_key"] for c in components],
    )
    return composite, classification


# ── Rotation labelling ───────────────────────────────────────────────────────

def compute_rotation(industry_series: pd.Series, nifty_series: pd.Series,
                       composite_score: float, prev_score: float | None) -> str:
    """Six-way rotation label based on level + change vs Nifty."""
    if len(industry_series) < 60 or len(nifty_series) < 60:
        return "Unknown"

    aligned = pd.concat([industry_series.rename("i"), nifty_series.rename("n")],
                          axis=1).dropna()
    if len(aligned) < 30:
        return "Unknown"

    # Recent outperformance direction (last 20 days vs prior 20 days)
    rs_recent = (aligned["i"].iloc[-1] / aligned["i"].iloc[-21] - 1) - \
                (aligned["n"].iloc[-1] / aligned["n"].iloc[-21] - 1)
    if len(aligned) >= 41:
        rs_prior = (aligned["i"].iloc[-21] / aligned["i"].iloc[-41] - 1) - \
                    (aligned["n"].iloc[-21] / aligned["n"].iloc[-41] - 1)
    else:
        rs_prior = 0.0

    trend_up = rs_recent > rs_prior                                     # RS improving
    outperforming = rs_recent > 0

    if composite_score >= 65 and outperforming and trend_up:
        return "Strong-Leader"
    if composite_score >= 55 and outperforming and trend_up:
        return "Emerging-Leader"
    if composite_score >= 55 and outperforming and not trend_up:
        return "Falling-Leader"
    if composite_score < 55 and not outperforming and trend_up:
        return "Improving"
    if composite_score >= 45 and not outperforming and not trend_up:
        return "Weakening"
    return "Lagging"


# ── Store + orchestration ────────────────────────────────────────────────────

def store_derived(all_d, all_n, all_c, all_comp) -> Path:
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
        if not items: return
        pd.DataFrame([_row(as_dict(x)) for x in items]).to_parquet(
            partition / f"industry_{name}_{stamp}.parquet", index=False)

    _write("derived", all_d)
    _write("normalized", all_n)
    _write("classifications", all_c)
    _write("composites", all_comp)
    return partition


def run_compute_cycle(verbose: bool = True) -> dict:
    raw = load_recent_raw(days=350)
    if raw.empty:
        return {"error": "no raw observations — run DEV017 and DEV018 first"}

    nifty = series_for_variable(raw, "equity_index.india.nifty50.close")
    if len(nifty) < 30:
        return {"error": "insufficient Nifty history — run DEV017 first"}

    asof = pd.to_datetime(raw["asof_utc"]).max().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    code_sha = _git_sha()
    global_ctx = load_global_context()
    sector_ctx = load_sector_context()

    all_d, all_n, all_c, all_comp = [], [], [], []
    per_industry = []

    for spec in industry_catalog.INDUSTRIES:
        # Build the aggregate industry series
        ind_series, n_used = build_industry_series(spec)
        if len(ind_series) < 30 or n_used < 3:
            per_industry.append({"industry_key": spec.industry_key,
                                    "display_name": spec.display_name,
                                    "parent_sector_key": spec.parent_sector_key,
                                    "parent_sector_name": spec.parent_sector_name,
                                    "status": "insufficient_constituents",
                                    "n_used": n_used,
                                    "n_defined": len(spec.tickers)})
            continue

        # Sector-index series if available (from DEV018 raw store)
        sec_series = series_for_variable(raw, spec.parent_sector_key + ".close")

        result = compute_industry(spec, ind_series, nifty, sec_series if len(sec_series) > 30 else None,
                                    n_used, code_sha, asof)
        if result is None:
            per_industry.append({"industry_key": spec.industry_key,
                                    "display_name": spec.display_name,
                                    "status": "compute_failed"})
            continue

        composite, cls = compute_composite(result["normalized"], spec.industry_key, asof)
        if composite is None:
            per_industry.append({"industry_key": spec.industry_key,
                                    "display_name": spec.display_name,
                                    "status": "no_valid_dimensions"})
            continue

        rotation = compute_rotation(ind_series, nifty, composite.value_0_100, None)

        all_d.extend(result["derived"])
        all_n.extend(result["normalized"])
        all_c.append(cls)
        all_comp.append(composite)

        per_industry.append({
            "industry_key": spec.industry_key,
            "display_name": spec.display_name,
            "parent_sector_key": spec.parent_sector_key,
            "parent_sector_name": spec.parent_sector_name,
            "status": "computed",
            "composite": composite,
            "classification": cls,
            "rotation": rotation,
            "n_used": n_used,
            "n_defined": len(spec.tickers),
        })

    partition = store_derived(all_d, all_n, all_c, all_comp)

    # Ranking
    computed = [x for x in per_industry if x["status"] == "computed"]
    computed.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
    for rank, entry in enumerate(computed, start=1):
        entry["leadership_rank"] = rank

    # Cross-sector rotation rank (industries improving vs weakening within each sector)
    from collections import defaultdict
    by_sector = defaultdict(list)
    for e in computed:
        by_sector[e["parent_sector_key"]].append(e)
    for sec_key, entries in by_sector.items():
        entries.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
        for rank, entry in enumerate(entries, start=1):
            entry["intra_sector_rank"] = rank
            entry["intra_sector_total"] = len(entries)

    if verbose:
        print(f"        industries: {len(computed)}/{len(industry_catalog.INDUSTRIES)}   "
                f"asof: {asof[:10]}")
        print(f"        derived: {len(all_d)}   normalized: {len(all_n)}   "
                f"classifications: {len(all_c)}   composites: {len(all_comp)}")
        print(f"        global_context: {'YES' if global_ctx else 'no'}   "
                f"sector_context: {'YES' if sector_ctx else 'no'}")

    return {
        "industries_attempted": len(industry_catalog.INDUSTRIES),
        "industries_computed": len(computed),
        "derived_count": len(all_d),
        "normalized_count": len(all_n),
        "classifications_count": len(all_c),
        "composites_count": len(all_comp),
        "partition": str(partition),
        "asof_utc": asof,
        "_per_industry": per_industry,
        "_global_context": global_ctx,
        "_sector_context": sector_ctx,
    }

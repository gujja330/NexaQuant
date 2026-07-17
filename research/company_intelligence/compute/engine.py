"""DEV020 compute engine.

For every mapped ticker, computes 11 dimensions and produces a composite score
with full context inheritance from DEV017/DEV018/DEV019.

Reuses ARCH017A entities from research/global_intelligence/lib.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
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
from industry_intelligence.compute import engine as industry_engine                # noqa: E402
from company_intelligence.lib import company_catalog                                # noqa: E402


RAW_DIR = _ROOT / "data" / "market_intelligence" / "raw"
DERIVED_DIR = _ROOT / "data" / "market_intelligence" / "derived"
CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"
GLOBAL_BUNDLE = _ROOT / "reports" / "global_context.json"
SECTOR_BUNDLE = _ROOT / "reports" / "sector_context.json"
INDUSTRY_BUNDLE = _ROOT / "reports" / "industry_context.json"


CLASS_ENUM = ["Strong-Bullish", "Bullish", "Neutral", "Weak", "Bearish", "Unknown"]

# 11-dimension weight table (v1 draft)
COMPOSITE_WEIGHTS_V1 = {
    "norm.company.momentum":       0.15,
    "norm.company.rs_industry":    0.12,
    "norm.company.rs_sector":      0.08,
    "norm.company.rs_nifty":       0.08,
    "norm.company.trend":          0.10,
    "norm.company.volatility":     0.08,
    "norm.company.drawdown":       0.08,
    "norm.company.52w_position":   0.08,
    "norm.company.liquidity":      0.06,
    "norm.company.volume_trend":   0.07,
    "norm.company.breakout":       0.05,
    "norm.company.technical":      0.05,
}


# ── Validation constants ────────────────────────────────────────────────────
MIN_HISTORY_BARS = 100
MIN_ADV_INR_CRORE = 1.0                                       # weak but non-zero
MIN_LATEST_CLOSE = 1.0                                        # sanity


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


# ── Data loading ─────────────────────────────────────────────────────────────

def load_ticker_ohlcv(ticker: str, n_days: int = 350) -> pd.DataFrame:
    parq = CONSTITUENT_PARQ_DIR / f"{ticker}_D1.parquet"
    if not parq.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(parq)
        if df.empty:
            return pd.DataFrame()
        return df.tail(n_days).copy()
    except Exception:
        return pd.DataFrame()


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


def series_for_variable(df: pd.DataFrame, variable_key: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    sub = df[df["variable_key"] == variable_key].copy()
    sub = sub.sort_values("asof_utc").drop_duplicates(subset=["asof_utc"], keep="last")
    return pd.Series(sub["value"].values.astype(float),
                      index=pd.to_datetime(sub["asof_utc"]).values,
                      name=variable_key)


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.load(path.open("r", encoding="utf-8"))
    except Exception:
        return None


# ── Metric primitives (borrowed from DEV018/019 patterns) ────────────────────

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


# ── Validation ───────────────────────────────────────────────────────────────

def validate_ticker(ticker: str, df: pd.DataFrame) -> tuple[bool, str]:
    if df.empty:
        return False, "no_data"
    if "close" not in df.columns:
        return False, "missing_close_column"
    close = df["close"].dropna()
    if len(close) < MIN_HISTORY_BARS:
        return False, f"insufficient_history({len(close)}<{MIN_HISTORY_BARS})"
    latest = float(close.iloc[-1])
    if latest < MIN_LATEST_CLOSE:
        return False, f"invalid_latest_close({latest})"
    if "tick_volume" in df.columns:
        # ADV in INR crore proxy: mean(close * volume) / 1e7 over 20 days
        vol = df["tick_volume"].dropna().tail(20)
        prc = df["close"].dropna().tail(20)
        if len(vol) >= 10 and len(prc) >= 10:
            adv_crore = float((prc.tail(len(vol)) * vol).mean() / 1e7)
            if adv_crore < MIN_ADV_INR_CRORE:
                return False, f"low_liquidity(adv_cr={adv_crore:.2f})"
    return True, "ok"


# ── Per-company compute ─────────────────────────────────────────────────────

def compute_company(spec: company_catalog.CompanySpec,
                     df: pd.DataFrame,
                     nifty_series: pd.Series,
                     sector_series: pd.Series | None,
                     industry_series: pd.Series | None,
                     code_sha: str, asof_iso: str) -> dict | None:
    close = df["close"].dropna()
    if len(close) < MIN_HISTORY_BARS:
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

    prefix = f"company.{spec.ticker}"
    latest_close = float(close.iloc[-1])

    # 1. Trend (MAs)
    ma_20 = _ma(close, 20); ma_50 = _ma(close, 50)
    ma_100 = _ma(close, 100); ma_200 = _ma(close, 200)
    for n, v in [(20, ma_20), (50, ma_50), (100, ma_100), (200, ma_200)]:
        _dm(f"derived.{prefix}.ma_{n}d", v, "INR", f"sma_{n}d")
    mas = [m for m in [ma_20, ma_50, ma_100, ma_200] if m is not None]
    trend_score = None
    if mas:
        above = sum(1 for m in mas if latest_close > m)
        trend_score = (above / len(mas)) * 100
        _ni("norm.company.trend", trend_score, method="mas_above_count")

    # 2. Momentum
    m20, m60, m120 = _roc(close, 20), _roc(close, 60), _roc(close, 120)
    _dm(f"derived.{prefix}.mom_20d", m20, "%", "roc_20d")
    _dm(f"derived.{prefix}.mom_60d", m60, "%", "roc_60d")
    _dm(f"derived.{prefix}.mom_120d", m120, "%", "roc_120d")

    m20s, m60s, m120s = (close.pct_change(20)*100, close.pct_change(60)*100,
                              close.pct_change(120)*100)
    ps = []
    for cur, series in [(m20, m20s), (m60, m60s), (m120, m120s)]:
        if cur is not None and len(series.dropna()) > 30:
            ps.append(_norm_percentile(series.dropna(), cur))
    mom_score = None
    if ps:
        mom_score = sum(ps) / len(ps)
        _ni("norm.company.momentum", mom_score)

    # 3. RS vs industry
    rs_ind_score = None
    if industry_series is not None and len(industry_series) > 30:
        rs20 = _rs_diff(close, industry_series, 20)
        rs60 = _rs_diff(close, industry_series, 60)
        _dm(f"derived.{prefix}.rs_industry_20d", rs20, "%_diff", "rs_20d")
        _dm(f"derived.{prefix}.rs_industry_60d", rs60, "%_diff", "rs_60d")
        if rs20 is not None:
            aligned = pd.concat([close.rename("c"), industry_series.rename("i")],
                                  axis=1).dropna()
            if len(aligned) >= 40:
                rs_hist = (aligned["c"].pct_change(20) - aligned["i"].pct_change(20)) * 100
                rs_ind_score = _norm_percentile(rs_hist.dropna(), rs20)
                _ni("norm.company.rs_industry", rs_ind_score)

    # 4. RS vs sector
    rs_sec_score = None
    if sector_series is not None and len(sector_series) > 30:
        rs20 = _rs_diff(close, sector_series, 20)
        _dm(f"derived.{prefix}.rs_sector_20d", rs20, "%_diff", "rs_20d")
        if rs20 is not None:
            aligned = pd.concat([close.rename("c"), sector_series.rename("s")],
                                  axis=1).dropna()
            if len(aligned) >= 40:
                rs_hist = (aligned["c"].pct_change(20) - aligned["s"].pct_change(20)) * 100
                rs_sec_score = _norm_percentile(rs_hist.dropna(), rs20)
                _ni("norm.company.rs_sector", rs_sec_score)

    # 5. RS vs Nifty
    rs_nifty_score = None
    if len(nifty_series) > 30:
        rs20 = _rs_diff(close, nifty_series, 20)
        _dm(f"derived.{prefix}.rs_nifty_20d", rs20, "%_diff", "rs_20d")
        if rs20 is not None:
            aligned = pd.concat([close.rename("c"), nifty_series.rename("n")],
                                  axis=1).dropna()
            if len(aligned) >= 40:
                rs_hist = (aligned["c"].pct_change(20) - aligned["n"].pct_change(20)) * 100
                rs_nifty_score = _norm_percentile(rs_hist.dropna(), rs20)
                _ni("norm.company.rs_nifty", rs_nifty_score)

    # 6. Volatility (inverted)
    vol = _realised_vol(close, 20)
    _dm(f"derived.{prefix}.vol_20d_ann", vol, "%_ann", "vol_20d_ann")
    if vol is not None:
        vs = (close.pct_change().rolling(20).std() * np.sqrt(252) * 100).dropna()
        if len(vs) >= 30:
            _ni("norm.company.volatility", 100.0 - _norm_percentile(vs, vol))

    # 7. Max drawdown (inverted)
    dd = _max_drawdown(close, 252)
    _dm(f"derived.{prefix}.max_dd_252d", dd, "%", "max_dd_252d")
    if dd is not None:
        _ni("norm.company.drawdown", _clamp(100.0 + dd * 2.5))

    # 8. 52w position
    pos = _pct_position_52w(close)
    _dm(f"derived.{prefix}.pos_52w", pos, "%", "position_52w")
    if pos is not None:
        _ni("norm.company.52w_position", pos)

    # 9. Liquidity (ADV in INR crore percentile)
    adv_score = None
    if "tick_volume" in df.columns:
        vol_s = df["tick_volume"].dropna()
        prc = df["close"].dropna()
        if len(vol_s) >= 30 and len(prc) >= 30:
            adv_series = (prc * vol_s.reindex(prc.index)).dropna().rolling(20).mean() / 1e7
            adv_series = adv_series.dropna()
            if len(adv_series) >= 30:
                adv_score = _norm_percentile(adv_series, float(adv_series.iloc[-1]))
                _dm(f"derived.{prefix}.adv_20d_inr_crore",
                    float(adv_series.iloc[-1]), "INR_crore", "adv_20d")
                _ni("norm.company.liquidity", adv_score)

    # 10. Volume trend (20d / 90d ratio)
    if "tick_volume" in df.columns:
        vol_s = df["tick_volume"].dropna()
        if len(vol_s) >= 90:
            v20 = float(vol_s.tail(20).mean())
            v90 = float(vol_s.tail(90).mean())
            if v90 > 0:
                ratio = v20 / v90
                _dm(f"derived.{prefix}.volume_ratio_20_90", ratio, "ratio", "vol_ratio")
                _ni("norm.company.volume_trend", _clamp((ratio - 0.5) * 100))

    # 11. Breakout status: % distance below 52-week high
    if pos is not None:
        # pos is [0, 100]; 100 = at 52w high (breakout candidate)
        _ni("norm.company.breakout", pos)                                   # same as 52w_position but semantic

    # Technical strength = blend of momentum + trend + RS_nifty
    tech_parts = [x for x in [mom_score, trend_score, rs_nifty_score] if x is not None]
    if tech_parts:
        tech = sum(tech_parts) / len(tech_parts)
        _dm(f"derived.{prefix}.technical_strength", tech, "score", "avg_of_mom_trend_rs")
        _ni("norm.company.technical", tech)

    # Risk score: aggregated risk (higher = safer)
    # Blend: volatility (inverted, already high=safe) + drawdown (already high=safe)
    n_map = {n.indicator_key: n.value_0_100 for n in normalized}
    risk_parts = []
    if "norm.company.volatility" in n_map:
        risk_parts.append(n_map["norm.company.volatility"])
    if "norm.company.drawdown" in n_map:
        risk_parts.append(n_map["norm.company.drawdown"])
    risk_score = sum(risk_parts) / len(risk_parts) if risk_parts else None

    return {
        "ticker": spec.ticker,
        "industry_key": spec.industry_key,
        "industry_display": spec.industry_display,
        "parent_sector_key": spec.parent_sector_key,
        "parent_sector_display": spec.parent_sector_display,
        "latest_close": latest_close,
        "history_bars": len(close),
        "adv_score": adv_score,
        "risk_score": risk_score,
        "derived": derived,
        "normalized": normalized,
    }


# ── Composite + classification ───────────────────────────────────────────────

def compute_composite(normalized_list, ticker: str, asof_iso: str
                        ) -> tuple[CompositeScore, Classification] | tuple[None, None]:
    if not normalized_list:
        return None, None
    n = {i.indicator_key: i for i in normalized_list}
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
        composite_key=f"composite.company.{ticker}.strength",
        asof_utc=asof_iso, value_0_100=round(score, 2),
        classification=label, confidence=round(conf, 3),
        weighting_scheme="expert_curated_v1", weighting_version="v1.0",
        component_indicators=components,
    )
    classification = Classification(
        key=f"classification.company.{ticker}", asof_utc=asof_iso, label=label,
        confidence=round(conf, 3),
        contributing_indicator_ids=[c["indicator_key"] for c in components],
    )
    return composite, classification


# ── Storage ──────────────────────────────────────────────────────────────────

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
            partition / f"company_{name}_{stamp}.parquet", index=False)

    _write("derived", all_d)
    _write("normalized", all_n)
    _write("classifications", all_c)
    _write("composites", all_comp)
    return partition


# ── Orchestration ────────────────────────────────────────────────────────────

def run_compute_cycle(verbose: bool = True, max_tickers: int | None = None) -> dict:
    raw = load_recent_raw(days=350)
    if raw.empty:
        return {"error": "no shared raw store — run DEV017 first"}
    nifty = series_for_variable(raw, "equity_index.india.nifty50.close")
    if len(nifty) < 30:
        return {"error": "insufficient Nifty history — run DEV017 first"}

    asof = pd.to_datetime(raw["asof_utc"]).max().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    code_sha = _git_sha()

    global_ctx = _load_json(GLOBAL_BUNDLE)
    sector_ctx = _load_json(SECTOR_BUNDLE)
    industry_ctx = _load_json(INDUSTRY_BUNDLE)

    # Build sector_series cache from raw store (DEV018 sector indices)
    sector_series_cache: dict[str, pd.Series] = {}

    # Build industry_series cache using DEV019's aggregation
    # (rebuild per industry once, then reuse for every company in that industry)
    industry_series_cache: dict[str, pd.Series] = {}
    from industry_intelligence.lib import industry_catalog as ic
    for ind_spec in ic.INDUSTRIES:
        s, n = industry_engine.build_industry_series(ind_spec)
        if n >= 3 and len(s) > 30:
            industry_series_cache[ind_spec.industry_key] = s

    # Sector lookup (from industry ctx)
    sector_score_lookup, sector_class_lookup = {}, {}
    if sector_ctx and "sectors" in sector_ctx:
        for s in sector_ctx["sectors"]:
            if s.get("status") != "computed": continue
            sector_score_lookup[s["sector_key"]] = s["score"]
            sector_class_lookup[s["sector_key"]] = s["classification"]

    industry_score_lookup, industry_class_lookup = {}, {}
    if industry_ctx and "industries" in industry_ctx:
        for i in industry_ctx["industries"]:
            if i.get("status") != "computed": continue
            industry_score_lookup[i["industry_key"]] = i["score"]
            industry_class_lookup[i["industry_key"]] = i["classification"]

    global_score = None
    global_posture = None
    if global_ctx:
        global_score = global_ctx.get("composites", {}).get("global_risk", {}).get("value_0_100")
        global_posture = global_ctx.get("classifications", {}).get("global_posture", {}).get("label")

    all_d, all_n, all_c, all_comp = [], [], [], []
    per_company = []
    rejections = defaultdict(int)

    universe = company_catalog.COMPANIES
    if max_tickers is not None:
        universe = universe[:max_tickers]

    for i, spec in enumerate(universe):
        if verbose and i % 50 == 0 and i > 0:
            print(f"        ... {i}/{len(universe)} tickers processed")

        df = load_ticker_ohlcv(spec.ticker)
        ok, reason = validate_ticker(spec.ticker, df)
        if not ok:
            rejections[reason] += 1
            per_company.append({"ticker": spec.ticker, "status": "rejected",
                                  "reason": reason,
                                  "industry_key": spec.industry_key,
                                  "parent_sector_key": spec.parent_sector_key})
            continue

        # Fetch sector series if cache miss
        if spec.parent_sector_key not in sector_series_cache:
            s = series_for_variable(raw, spec.parent_sector_key + ".close")
            if len(s) >= 30:
                sector_series_cache[spec.parent_sector_key] = s
            else:
                sector_series_cache[spec.parent_sector_key] = None

        sec_series = sector_series_cache.get(spec.parent_sector_key)
        ind_series = industry_series_cache.get(spec.industry_key)

        result = compute_company(spec, df, nifty, sec_series, ind_series, code_sha, asof)
        if result is None:
            rejections["compute_failed"] += 1
            per_company.append({"ticker": spec.ticker, "status": "compute_failed",
                                  "industry_key": spec.industry_key,
                                  "parent_sector_key": spec.parent_sector_key})
            continue

        composite, cls = compute_composite(result["normalized"], spec.ticker, asof)
        if composite is None:
            rejections["no_valid_dimensions"] += 1
            per_company.append({"ticker": spec.ticker, "status": "no_valid_dimensions",
                                  "industry_key": spec.industry_key,
                                  "parent_sector_key": spec.parent_sector_key})
            continue

        all_d.extend(result["derived"])
        all_n.extend(result["normalized"])
        all_c.append(cls)
        all_comp.append(composite)

        per_company.append({
            "ticker": spec.ticker,
            "status": "computed",
            "industry_key": spec.industry_key,
            "industry_display": spec.industry_display,
            "parent_sector_key": spec.parent_sector_key,
            "parent_sector_display": spec.parent_sector_display,
            "composite": composite,
            "classification": cls,
            "latest_close": result["latest_close"],
            "history_bars": result["history_bars"],
            "adv_score": result["adv_score"],
            "risk_score": result["risk_score"],
            # inherited context
            "inherited_global_score": global_score,
            "inherited_global_posture": global_posture,
            "inherited_sector_score": sector_score_lookup.get(spec.parent_sector_key),
            "inherited_sector_class": sector_class_lookup.get(spec.parent_sector_key),
            "inherited_industry_score": industry_score_lookup.get(spec.industry_key),
            "inherited_industry_class": industry_class_lookup.get(spec.industry_key),
        })

    # Rankings
    computed = [c for c in per_company if c["status"] == "computed"]
    computed.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
    for rank, e in enumerate(computed, start=1):
        e["overall_rank"] = rank

    by_sector: dict[str, list] = defaultdict(list)
    by_industry: dict[str, list] = defaultdict(list)
    for e in computed:
        by_sector[e["parent_sector_key"]].append(e)
        by_industry[e["industry_key"]].append(e)
    for sec_key, entries in by_sector.items():
        entries.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
        for rank, e in enumerate(entries, start=1):
            e["sector_rank"] = rank
            e["sector_total"] = len(entries)
    for ind_key, entries in by_industry.items():
        entries.sort(key=lambda x: x["composite"].value_0_100, reverse=True)
        for rank, e in enumerate(entries, start=1):
            e["industry_rank"] = rank
            e["industry_total"] = len(entries)

    # RS rank (average of 3 RS scores)
    def _rs_avg(entry):
        parts = []
        for c in entry["composite"].component_indicators:
            if c["indicator_key"] in ("norm.company.rs_industry",
                                       "norm.company.rs_sector",
                                       "norm.company.rs_nifty"):
                parts.append(c["value_0_100"])
        return sum(parts) / len(parts) if parts else 0.0
    computed_rs = sorted(computed, key=_rs_avg, reverse=True)
    for rank, e in enumerate(computed_rs, start=1):
        e["rs_rank"] = rank

    # Risk rank (lower risk_score = higher risk; risk_rank 1 = safest)
    computed_risk = sorted(computed, key=lambda x: x["risk_score"] or 0, reverse=True)
    for rank, e in enumerate(computed_risk, start=1):
        e["risk_rank"] = rank

    partition = store_derived(all_d, all_n, all_c, all_comp)

    if verbose:
        print(f"        companies: {len(computed)}/{len(universe)}   asof: {asof[:10]}")
        print(f"        rejections: {dict(rejections)}")
        print(f"        derived: {len(all_d)}   normalized: {len(all_n)}   "
                f"composites: {len(all_comp)}")

    return {
        "companies_attempted": len(universe),
        "companies_computed": len(computed),
        "rejections": dict(rejections),
        "derived_count": len(all_d),
        "normalized_count": len(all_n),
        "classifications_count": len(all_c),
        "composites_count": len(all_comp),
        "partition": str(partition),
        "asof_utc": asof,
        "_per_company": per_company,
        "_global_context": global_ctx,
        "_sector_context": sector_ctx,
        "_industry_context": industry_ctx,
    }

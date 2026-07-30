"""Correlation Lab · multi-dimensional refinement analysis.

Answers the operator's CEO ask: correlate intraday↔delivery across every
dimension the recommendation engine already computes — sectors, industries,
technical scores, execution-flags (fills/drills), confidence buckets,
holding-period buckets — and surface the top refinement levers.

Uses daily OHLC bars from data/raw/india to compute:
  · intraday_ret = (close − open) / open       (single-bar proxy)
  · overnight_gap = (open − prev_close) / prev_close

Correlates against the swing return_pct from reports/learning.parquet
sliced across every meaningful dimension in the corpus.

Output: reports/research/intraday_delivery_correlation.json
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.research.correlation_lab.v1.20260731"
ENGINE_ID = "aegis.research.correlation_lab.v1"

ORC_MIN_INTRADAY_PCT = 0.0
GAP_MAX_PCT = 2.0
MEANINGFUL_UPLIFT_PP = 0.5


def _normalize_ticker(t: str) -> str:
    if not t:
        return ""
    t = t.strip()
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if t.upper().endswith(suffix):
            return t[: -len(suffix)]
    return t


def _load_ticker_ohlc_row(root: Path, ticker: str, entry_dt) -> tuple[float, float, float] | None:
    try:
        import pandas as pd
    except ImportError:
        return None
    p = root / "data" / "raw" / "india" / f"{_normalize_ticker(ticker)}_D1.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        idx = df.index[df.index <= entry_dt]
        if len(idx) < 2:
            return None
        prev = df.loc[idx[-2]]
        cur = df.loc[idx[-1]]
        return float(prev["close"]), float(cur["open"]), float(cur["close"])
    except Exception:
        return None


@dataclass
class FilterUplift:
    filter_name: str
    n_before: int
    n_after: int
    median_before_pct: float
    median_after_pct: float
    win_rate_before: float
    win_rate_after: float
    uplift_median_pp: float
    uplift_win_rate_pp: float
    verdict: str
    recommendation: str


@dataclass
class CorrelationReport:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    market: str = "india"
    n_trades_evaluated: int = 0
    pearson_intraday_vs_swing: float | None = None
    spearman_intraday_vs_swing: float | None = None
    interpretation: str = ""
    filters: list = field(default_factory=list)
    best_filter: str | None = None
    hybrid_strategy_recommendation: str = ""
    by_sector: list = field(default_factory=list)
    by_industry: list = field(default_factory=list)
    by_dimension_score: list = field(default_factory=list)
    by_execution_flags: list = field(default_factory=list)
    by_confidence_bucket: list = field(default_factory=list)
    by_holding_period_bucket: list = field(default_factory=list)
    top_refinement_levers: list = field(default_factory=list)


def _compute_uplift(name: str, mask, base_returns) -> FilterUplift:
    n_before = len(base_returns)
    filtered = base_returns[mask]
    n_after = len(filtered)
    med_b = float(base_returns.median()) if n_before else 0.0
    med_a = float(filtered.median()) if n_after else 0.0
    wr_b = float((base_returns > 0).mean()) if n_before else 0.0
    wr_a = float((filtered > 0).mean()) if n_after else 0.0
    uplift_med = med_a - med_b
    uplift_wr = wr_a - wr_b
    if uplift_med > MEANINGFUL_UPLIFT_PP and uplift_wr > 0.02 and n_after >= 30:
        verdict = "material_uplift"
        rec = f"SHIP FILTER · median +{uplift_med:.2f}pp · win-rate +{uplift_wr*100:.1f}pp"
    elif uplift_med > 0 or uplift_wr > 0:
        verdict = "marginal_uplift"
        rec = "Marginal · monitor further · not decision-grade"
    else:
        verdict = "no_uplift_or_harmful"
        rec = "REJECT · filter does not improve the corpus"
    return FilterUplift(
        filter_name=name, n_before=n_before, n_after=n_after,
        median_before_pct=round(med_b, 3), median_after_pct=round(med_a, 3),
        win_rate_before=round(wr_b, 4), win_rate_after=round(wr_a, 4),
        uplift_median_pp=round(uplift_med, 3),
        uplift_win_rate_pp=round(uplift_wr, 4),
        verdict=verdict, recommendation=rec,
    )


def compute_intraday_delivery_correlation(root: Path,
                                              market: str = "india") -> CorrelationReport:
    import pandas as pd
    rep = CorrelationReport(run_utc=datetime.now(timezone.utc).isoformat(),
                                 market=market)
    lp = root / "reports" / "learning.parquet"
    if not lp.exists():
        rep.interpretation = "learning_parquet_missing"
        return rep

    try:
        df = pd.read_parquet(lp)
    except Exception:
        rep.interpretation = "learning_parquet_unreadable"
        return rep

    needed = {"ticker", "entry_date", "return_pct"}
    if not needed.issubset(df.columns):
        rep.interpretation = f"missing_columns · needs {sorted(needed)}"
        return rep

    df = df.dropna(subset=list(needed)).copy()
    df["entry_dt"] = pd.to_datetime(df["entry_date"], errors="coerce")
    df = df.dropna(subset=["entry_dt"])

    dim_cols = [c for c in df.columns if c.startswith("dim_")]
    aux_cols = [c for c in ("sector", "industry", "confidence", "score_at_entry",
                              "mfe_pct", "mae_pct", "n_bars_held",
                              "hit_5pct_target", "hit_10pct_target",
                              "hit_5pct_stop", "hit_10pct_stop", "is_winner")
                    if c in df.columns]

    rows = []
    for _, r in df.iterrows():
        bar = _load_ticker_ohlc_row(root, str(r["ticker"]), r["entry_dt"])
        if bar is None:
            continue
        prev_close, opn, cls = bar
        if not (prev_close > 0 and opn > 0):
            continue
        intraday_pct = (cls - opn) / opn * 100
        gap_pct = (opn - prev_close) / prev_close * 100
        row = {
            "ticker":       r["ticker"],
            "swing_ret":    float(r["return_pct"]),
            "intraday":     intraday_pct,
            "gap":          gap_pct,
        }
        for c in aux_cols + dim_cols:
            row[c] = r.get(c)
        rows.append(row)

    if len(rows) < 30:
        rep.interpretation = "insufficient_paired_bars"
        rep.n_trades_evaluated = len(rows)
        return rep

    pairs = pd.DataFrame(rows)
    rep.n_trades_evaluated = len(pairs)

    pear = float(pairs["intraday"].corr(pairs["swing_ret"]))
    spear = float(pairs["intraday"].corr(pairs["swing_ret"], method="spearman"))
    rep.pearson_intraday_vs_swing = round(pear if pear == pear else 0.0, 4)
    rep.spearman_intraday_vs_swing = round(spear if spear == spear else 0.0, 4)

    abs_r = abs(rep.pearson_intraday_vs_swing)
    if abs_r < 0.05:
        rep.interpretation = ("intraday_and_swing_independent · intraday direction "
                                "carries almost NO information about the swing outcome. "
                                "Same-day confirmation filters unlikely to help globally · "
                                "check by_sector for pocket levers.")
    elif abs_r < 0.15:
        rep.interpretation = ("weak_positive_correlation · worth testing ORC as a soft filter")
    else:
        rep.interpretation = ("meaningful_correlation · hybrid ORC filter is a high-conviction "
                                "refinement candidate")

    base = pairs["swing_ret"]

    # Broad filters
    orc_mask = pairs["intraday"] > ORC_MIN_INTRADAY_PCT
    rep.filters.append(asdict(_compute_uplift("opening_range_confirmation_intraday_gt_0",
                                                    orc_mask, base)))
    gap_mask = pairs["gap"] <= GAP_MAX_PCT
    rep.filters.append(asdict(_compute_uplift(f"skip_gap_up_over_{GAP_MAX_PCT}pct",
                                                    gap_mask, base)))
    combined_mask = orc_mask & gap_mask
    rep.filters.append(asdict(_compute_uplift("hybrid_orc_plus_gap_filter",
                                                    combined_mask, base)))
    anti_mask = pairs["intraday"] < 0
    rep.filters.append(asdict(_compute_uplift("what_if_we_still_bought_when_intraday_negative",
                                                    anti_mask, base)))

    # Multi-dim slicing
    def _slice(df_group, group_val, group_key):
        if len(df_group) < 20:
            return None
        pear_g = float(df_group["intraday"].corr(df_group["swing_ret"]))
        if pear_g != pear_g:
            pear_g = 0.0
        orc = df_group["intraday"] > ORC_MIN_INTRADAY_PCT
        b = df_group["swing_ret"]
        f = b[orc]
        med_b = float(b.median())
        med_a = float(f.median()) if len(f) else med_b
        wr_b = float((b > 0).mean())
        wr_a = float((f > 0).mean()) if len(f) else wr_b
        return {
            group_key: str(group_val), "n": int(len(df_group)),
            "pearson": round(pear_g, 4),
            "median_ret_pct": round(med_b, 3), "win_rate": round(wr_b, 4),
            "orc_median_uplift": round(med_a - med_b, 3),
            "orc_win_uplift": round(wr_a - wr_b, 4),
            "orc_n_after": int(len(f)),
        }

    def _bucketize(series, edges, labels):
        import pandas as pd
        return pd.cut(series, bins=edges, labels=labels, include_lowest=True)

    if "sector" in pairs.columns:
        for sec, sub in pairs.groupby("sector"):
            s = _slice(sub, sec, "sector")
            if s: rep.by_sector.append(s)
        rep.by_sector.sort(key=lambda x: abs(x.get("orc_median_uplift", 0)), reverse=True)

    if "industry" in pairs.columns:
        for ind, sub in pairs.groupby("industry"):
            s = _slice(sub, ind, "industry")
            if s: rep.by_industry.append(s)
        rep.by_industry.sort(key=lambda x: abs(x.get("orc_median_uplift", 0)), reverse=True)
        rep.by_industry = rep.by_industry[:15]

    for dcol in dim_cols:
        try:
            ser = pairs[dcol].dropna()
            if len(ser) < 30:
                continue
            q33, q67 = ser.quantile([0.33, 0.67])
            buckets = _bucketize(pairs[dcol], [-1e9, q33, q67, 1e9], ["LOW", "MID", "HIGH"])
            for lvl, sub in pairs.groupby(buckets, observed=True):
                s = _slice(sub, f"{dcol}={lvl}", "dimension_bucket")
                if s: rep.by_dimension_score.append(s)
        except Exception:
            continue
    rep.by_dimension_score.sort(key=lambda x: abs(x.get("orc_median_uplift", 0)), reverse=True)
    rep.by_dimension_score = rep.by_dimension_score[:20]

    for flag in ("hit_5pct_target", "hit_10pct_target",
                    "hit_5pct_stop", "hit_10pct_stop"):
        if flag in pairs.columns:
            for hit_val, sub in pairs.groupby(pairs[flag].fillna(False).astype(bool)):
                s = _slice(sub, f"{flag}={hit_val}", "execution_flag")
                if s: rep.by_execution_flags.append(s)

    if "confidence" in pairs.columns and pairs["confidence"].notna().sum() >= 30:
        try:
            conf = pairs["confidence"].dropna()
            q33, q67 = conf.quantile([0.33, 0.67])
            buckets = _bucketize(pairs["confidence"], [-1e9, q33, q67, 1e9],
                                    ["LOW_CONF", "MID_CONF", "HIGH_CONF"])
            for lvl, sub in pairs.groupby(buckets, observed=True):
                s = _slice(sub, str(lvl), "confidence_bucket")
                if s: rep.by_confidence_bucket.append(s)
        except Exception:
            pass

    if "n_bars_held" in pairs.columns and pairs["n_bars_held"].notna().sum() >= 30:
        try:
            buckets = _bucketize(pairs["n_bars_held"], [-1, 5, 15, 1e9],
                                    ["SHORT_1_5d", "MEDIUM_6_15d", "LONG_16d_plus"])
            for lvl, sub in pairs.groupby(buckets, observed=True):
                s = _slice(sub, str(lvl), "holding_bucket")
                if s: rep.by_holding_period_bucket.append(s)
        except Exception:
            pass

    all_slices = []
    for s in rep.by_sector:            all_slices.append(("sector", s))
    for s in rep.by_industry:          all_slices.append(("industry", s))
    for s in rep.by_dimension_score:   all_slices.append(("dimension", s))
    for s in rep.by_execution_flags:   all_slices.append(("execution_flag", s))
    for s in rep.by_confidence_bucket: all_slices.append(("confidence", s))
    for s in rep.by_holding_period_bucket: all_slices.append(("holding", s))
    strong = [(cat, s) for (cat, s) in all_slices
                 if s.get("orc_median_uplift", 0) >= MEANINGFUL_UPLIFT_PP
                 and s.get("orc_n_after", 0) >= 30]
    strong.sort(key=lambda x: x[1].get("orc_median_uplift", 0), reverse=True)
    rep.top_refinement_levers = [
        {
            "category":  cat,
            "slice":     {k: v for k, v in s.items() if k != "orc_n_after"},
            "recommendation": (f"HIGH-CONVICTION REFINEMENT · apply ORC within this slice · "
                                     f"+{s.get('orc_median_uplift', 0):.2f}pp median · "
                                     f"+{s.get('orc_win_uplift', 0)*100:.1f}pp win-rate"),
        }
        for cat, s in strong[:10]
    ]

    material = [f for f in rep.filters if f["verdict"] == "material_uplift"
                    and f["filter_name"] != "what_if_we_still_bought_when_intraday_negative"]
    if material:
        best = max(material, key=lambda f: f["uplift_median_pp"])
        rep.best_filter = best["filter_name"]
        rep.hybrid_strategy_recommendation = (
            f"BROAD FILTER CANDIDATE: {best['filter_name']} · +"
            f"{best['uplift_median_pp']:.2f}pp median · +{best['uplift_win_rate_pp']*100:.1f}pp "
            f"win-rate on {best['n_after']} of {best['n_before']} trades. "
            "Requires Article IX Research-Lifecycle promotion.")
    elif rep.top_refinement_levers:
        rep.hybrid_strategy_recommendation = (
            f"NO BROAD FILTER · but {len(rep.top_refinement_levers)} sector/dimension pockets "
            "show ORC uplift · candidate for narrow refinement research tickets.")
    else:
        rep.hybrid_strategy_recommendation = (
            "NO REFINEMENT LEVER DETECTED · corpus offers no decision-grade filter today. "
            "Re-run monthly as corpus grows.")
    return rep


def run_intraday_delivery_correlation(root: Path, market: str = "india") -> dict:
    out_dir = root / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = compute_intraday_delivery_correlation(root, market)
    (out_dir / "intraday_delivery_correlation.json").write_text(
        json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return asdict(rep)

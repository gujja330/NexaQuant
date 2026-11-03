"""Market-configurable top-stock selection from the daily feature snapshot.

CEO 2026-11-03 · WHAT THIS IS, AND WHAT IT IS NOT A FIX FOR
-----------------------------------------------------------
Measured first, as instructed. On 2026-11-03 the USA pipeline processed its
FULL universe end to end:

    feature snapshot   516 rows / 81 columns   · 100% of the universe
    recommendations    516 of 516 scored       · 12 BUY · 6 SELL · 498 HOLD

Ingestion, universe construction, feature generation and scoring all
complete at full size. USA's delivery failures were downstream of all of
it - the I28 gate, a market-blind health path, a half-cent rounding
mismatch and discarded artefacts. So shortlisting is NOT a fix for the
delivery problem and must not be presented as one.

It is a legitimate research question on its own terms: does a smaller,
higher-quality universe produce better decisions? That is what this
component exists to let us measure. India, for reference, scored 228 of
228 and produced ZERO actionable calls, so "India succeeds" is not
evidence that a smaller universe decides better.

DESIGN
------
Selection reads the daily feature snapshot, which is already point-in-time:
one row per (market, ticker) stamped with `asof`, built by the feature
store from data available at that date. Consuming it means this module
cannot introduce lookahead that the snapshot does not already contain, and
it adds no new data plumbing.

The full universe remains the source population. Selection returns a
SHORTLIST plus a complete audit of what was excluded and why. Nothing is
deleted, and nothing here touches the historical registry: an episode
excluded from today's shortlist stays in PIE's backtest population.

Scores are computed from features only. A missing feature never becomes a
zero - the component abstains from that criterion for that ticker and the
abstention is recorded, because scoring a gap as zero is indistinguishable
from scoring it as bad.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

SELECTION_VERSION = "1.0.0"

#: Per-market defaults. `top_n: None` means "the full eligible universe",
#: which is the current production behaviour for both markets.
DEFAULTS = {
    "india": {"top_n": None, "min_price": 0.0, "min_dollar_volume": 0.0,
              "max_per_sector": None, "min_completeness": 0.60},
    "usa": {"top_n": None, "min_price": 0.0, "min_dollar_volume": 0.0,
            "max_per_sector": None, "min_completeness": 0.60},
}

CONFIG_REL = ("config", "universe_selection.json")

#: Criterion -> the features it needs. A ticker missing all of a
#: criterion's inputs abstains from that criterion rather than scoring 0.
CRITERIA = {
    "liquidity": ("close", "volume"),
    "momentum": ("return_20d_pct", "return_60d_pct"),
    "trend": ("adx_14", "price_above_sma50", "price_above_sma200"),
    "risk": ("volatility_20d", "max_drawdown_60d_pct"),
    "evidence": ("hist_ticker_win_rate", "hist_ticker_n_trades"),
}

#: Weights are a starting hypothesis, not a validated optimum.
WEIGHTS = {"liquidity": 0.25, "momentum": 0.25, "trend": 0.20,
           "risk": 0.15, "evidence": 0.15}

EXCL_STALE = "STALE_ASOF"
EXCL_DUPLICATE = "DUPLICATE_TICKER"
EXCL_PRICE = "BELOW_MIN_PRICE"
EXCL_LIQUIDITY = "BELOW_MIN_DOLLAR_VOLUME"
EXCL_COMPLETENESS = "INSUFFICIENT_DATA_COMPLETENESS"
EXCL_SECTOR_CAP = "SECTOR_CAP_REACHED"
EXCL_RANK = "BELOW_TOP_N"


def load_config(root: Path, market: str) -> dict:
    """Defaults, overlaid by config/universe_selection.json when present."""
    cfg = dict(DEFAULTS.get(str(market).lower(), DEFAULTS["usa"]))
    p = Path(root).joinpath(*CONFIG_REL)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            cfg.update(raw.get(str(market).lower()) or {})
        except Exception:
            pass          # a malformed override must not silently resize
    return cfg                                      # the universe


def audit_dir(root: Path) -> Path:
    return Path(root) / "reports" / "universe"


def audit_path(root: Path, market: str, asof: str) -> Path:
    return audit_dir(root) / ("selection_%s_%s.json"
                             % (str(market).lower(), str(asof)[:10]))


def _pct_rank(s: pd.Series) -> pd.Series:
    """Rank to [0, 1]; NaN stays NaN so abstention survives scoring."""
    return s.rank(pct=True, na_option="keep")


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-criterion scores, an abstention list and a total.

    Cross-sectional ranking within the day's own universe, so the scale is
    defined by the population being chosen from rather than by any
    absolute threshold carried over from another date or market.
    """
    out = df.copy()

    def have(col):
        return col in out.columns

    liq = (out["close"] * out["volume"]) if (have("close") and have("volume")) \
        else pd.Series([float("nan")] * len(out), index=out.index)
    out["_dollar_volume"] = liq
    out["score_liquidity"] = _pct_rank(liq)

    mom = [c for c in ("return_20d_pct", "return_60d_pct") if have(c)]
    out["score_momentum"] = (
        pd.concat([_pct_rank(out[c]) for c in mom], axis=1).mean(axis=1)
        if mom else float("nan"))

    trend_parts = []
    if have("adx_14"):
        trend_parts.append(_pct_rank(out["adx_14"]))
    for c in ("price_above_sma50", "price_above_sma200"):
        if have(c):
            trend_parts.append(out[c].astype("float64").where(out[c].notna()))
    out["score_trend"] = (pd.concat(trend_parts, axis=1).mean(axis=1)
                          if trend_parts else float("nan"))

    risk_parts = []
    if have("volatility_20d"):
        risk_parts.append(1.0 - _pct_rank(out["volatility_20d"]))
    if have("max_drawdown_60d_pct"):
        # drawdown is negative · a shallower drawdown must rank higher
        risk_parts.append(_pct_rank(out["max_drawdown_60d_pct"]))
    out["score_risk"] = (pd.concat(risk_parts, axis=1).mean(axis=1)
                         if risk_parts else float("nan"))

    if have("hist_ticker_win_rate") and have("hist_ticker_n_trades"):
        n = out["hist_ticker_n_trades"].astype("float64")
        wr = out["hist_ticker_win_rate"].astype("float64")
        # Shrink towards 0.5 by sample size · 3 trades is not an edge.
        shrunk = (wr * n + 0.5 * 5.0) / (n + 5.0)
        out["score_evidence"] = _pct_rank(shrunk.where(wr.notna()))
    else:
        out["score_evidence"] = float("nan")

    abst, totals = [], []
    for _, r in out.iterrows():
        miss = [k for k in CRITERIA if pd.isna(r.get("score_%s" % k))]
        abst.append(miss)
        w = {k: v for k, v in WEIGHTS.items() if k not in miss}
        tw = sum(w.values())
        totals.append(float("nan") if not tw else
                      sum(r["score_%s" % k] * v for k, v in w.items()) / tw)
    out["abstained_criteria"] = abst
    out["selection_score"] = totals
    return out


def select(root: Path, market: str, snapshot: pd.DataFrame,
           asof: str, config: Optional[dict] = None) -> tuple:
    """(selected_df, audit_dict). Deterministic for a given input."""
    mkt = str(market).lower()
    cfg = dict(config or load_config(Path(root), mkt))
    df = snapshot.copy()
    total_in = len(df)
    excluded = []

    def drop(mask, reason):
        nonlocal df
        if mask.any():
            for _, r in df[mask].iterrows():
                excluded.append({"ticker": str(r.get("ticker")),
                                 "reason": reason})
            df = df[~mask]

    # stale rows · a snapshot row for another date is not today's evidence
    if "asof" in df.columns:
        drop(df["asof"].astype(str).str[:10] != str(asof)[:10], EXCL_STALE)
    # duplicate identity · keep the first, record the rest
    if "ticker" in df.columns:
        drop(df["ticker"].duplicated(keep="first"), EXCL_DUPLICATE)

    need = sorted({c for cols in CRITERIA.values() for c in cols
                   if c in df.columns})
    if need:
        comp = df[need].notna().mean(axis=1)
        df["data_completeness"] = comp
        drop(comp < float(cfg.get("min_completeness") or 0.0),
             EXCL_COMPLETENESS)
    else:
        df["data_completeness"] = float("nan")

    if "close" in df.columns and cfg.get("min_price"):
        drop(df["close"].fillna(-1) < float(cfg["min_price"]), EXCL_PRICE)

    df = score(df)
    if cfg.get("min_dollar_volume"):
        drop(df["_dollar_volume"].fillna(-1) < float(cfg["min_dollar_volume"]),
             EXCL_LIQUIDITY)

    eligible = len(df)
    # Deterministic order: score desc, then ticker for ties.
    df = df.sort_values(["selection_score", "ticker"],
                        ascending=[False, True], na_position="last")

    cap = cfg.get("max_per_sector")
    top_n = cfg.get("top_n")
    keep_idx, per_sector = [], {}
    for idx, r in df.iterrows():
        if top_n is not None and len(keep_idx) >= int(top_n):
            excluded.append({"ticker": str(r.get("ticker")),
                             "reason": EXCL_RANK})
            continue
        sec = str(r.get("sector") or "UNKNOWN")
        if cap is not None and per_sector.get(sec, 0) >= int(cap):
            excluded.append({"ticker": str(r.get("ticker")),
                             "reason": EXCL_SECTOR_CAP, "sector": sec})
            continue
        per_sector[sec] = per_sector.get(sec, 0) + 1
        keep_idx.append(idx)

    sel = df.loc[keep_idx]
    audit = {
        "market": mkt,
        "asof": str(asof)[:10],
        "selection_version": SELECTION_VERSION,
        "config": {k: cfg.get(k) for k in sorted(cfg)},
        "weights": dict(WEIGHTS),
        "universe_in": total_in,
        "eligible": eligible,
        "selected": len(sel),
        "excluded": len(excluded),
        "exclusion_reasons": {},
        "feature_set_version": (str(snapshot["feature_set_version"].iloc[0])
                                if "feature_set_version" in snapshot.columns
                                and len(snapshot) else None),
        "sector_distribution": dict(sorted(per_sector.items())),
        "data_completeness_mean": (None if sel.empty else
                                   float(sel["data_completeness"].mean())),
        "abstention_counts": {},
        "selected_tickers": [str(t) for t in sel.get("ticker", [])],
        "selected_evidence": [],
        "excluded_detail": excluded[:2000],
        "selected_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for e in excluded:
        r = e["reason"]
        audit["exclusion_reasons"][r] = audit["exclusion_reasons"].get(r, 0) + 1
    for k in CRITERIA:
        audit["abstention_counts"][k] = int(sum(
            1 for a in sel.get("abstained_criteria", []) if k in a))
    for _, r in sel.iterrows():
        audit["selected_evidence"].append({
            "ticker": str(r.get("ticker")),
            "sector": str(r.get("sector") or "UNKNOWN"),
            "selection_score": (None if pd.isna(r.get("selection_score"))
                                else round(float(r["selection_score"]), 6)),
            "components": {k: (None if pd.isna(r.get("score_%s" % k))
                               else round(float(r["score_%s" % k]), 6))
                           for k in CRITERIA},
            "abstained": list(r.get("abstained_criteria") or []),
            "data_completeness": (None if pd.isna(r.get("data_completeness"))
                                  else round(float(r["data_completeness"]), 4)),
        })
    return sel, audit


def write_audit(root: Path, market: str, asof: str, audit: dict) -> Path:
    d = audit_dir(Path(root))
    d.mkdir(parents=True, exist_ok=True)
    p = audit_path(Path(root), market, asof)
    p.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    return p

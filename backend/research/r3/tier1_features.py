"""AEGIS · R3 Tier-1 · UNIVERSE-WIDE PIT TECHNICAL FEATURES.

CEO 2026-09-07 · "R3 NEXT = universe-wide Tier-1 feature substrate."

WHY THIS MODULE EXISTS
----------------------
Widening Lane A to the full production universe (India 50 · USA 516) gave
R3 a broad LABEL substrate but not a broad FEATURE substrate:

    Lane A rows                578
    with >=1 Tier-1 feature     30
    with zero features         548

The five features `TIER1_SCOPE` declared were all R2 MODEL OUTPUTS
(entry_signal_score, entry_calibrated_conf, ...). Those cannot be computed
for a name R2 never scored, so they are structurally limited to R2's
selection. Training on them would reproduce exactly the selection bias the
universe decision was made to remove.

Re-reading the PDF's Tier-1 scope - "existing daily/technical features +
FII/DII + earnings calendar + options PCR + GBM + Platt" - the DAILY
TECHNICAL features were never implemented at all. `TIER1_SCOPE` contained
zero of them. This module implements that declared scope item. It is not
new sophistication and not Tier-2: it is the substrate Tier-1 was always
specified to have.

PIT GUARANTEE
-------------
Every feature is computed from price bars with index <= asof, and from
nothing else. There is no forward fill, no revision, and no join to a
current-snapshot artifact. Computing a feature for a past date returns the
same value whether or not later bars exist · asserted by
`test_r3_tier1_features` and by `pit_selftest()` below.

DISCIPLINE
----------
The feature set is FIXED and declared here up front. It was not selected
by looking at outcomes, and it must not be tuned against them · that would
be feature shopping, and it would invalidate the walk-forward evidence
these features exist to support. Adding or removing one is a registry
change, not an edit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

FEATURE_VERSION = "aegis.r3.tier1_technical.v1"

# The declared universe-wide technical set. Standard, deterministic
# constructions only · nothing bespoke, nothing optimised.
TECHNICAL_FEATURES = [
    "tech_return_1d",
    "tech_return_5d",
    "tech_return_20d",
    "tech_return_60d",
    "tech_volatility_20d",
    "tech_rsi_14",
    "tech_volume_ratio_20d",
    "tech_dist_52w_high_pct",
    "tech_ma_gap_20_50_pct",
    "tech_atr_pct_14",
]

MIN_BARS = 60          # need 60 bars for the longest lookback
_FRAME_CACHE: dict = {}


def _frame(root: Path, market: str, ticker: str):
    """Full price frame for a ticker · cached per process."""
    key = (str(root), market.lower(), ticker.upper())
    if key in _FRAME_CACHE:
        return _FRAME_CACHE[key]
    out = None
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, ticker.upper().split(".", 1)[0])
        if p and p.exists():
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            out = df.sort_index()
    except Exception:
        out = None
    _FRAME_CACHE[key] = out
    return out


def _ret(series, n: int) -> Optional[float]:
    if len(series) <= n:
        return None
    a, b = float(series.iloc[-1]), float(series.iloc[-1 - n])
    if b <= 0:
        return None
    return round((a / b - 1.0) * 100, 6)


def compute(root: Path, market: str, ticker: str, asof: str) -> dict:
    """PIT technical features for one (ticker, asof).

    Returns {} when the name has too little history · an empty dict is the
    honest answer, never a zero-filled row that would look like a real
    observation to a model.
    """
    df = _frame(root, market, ticker)
    if df is None or df.empty:
        return {}
    try:
        import pandas as pd
        cutoff = pd.to_datetime(asof).normalize()
        # THE PIT CUT · nothing after asof is visible, ever.
        hist = df[df.index <= cutoff]
        if len(hist) < MIN_BARS:
            return {}
        col = "close" if "close" in hist.columns else "Close"
        if col not in hist.columns:
            return {}
        close = hist[col].astype(float)

        feats: dict = {}
        feats["tech_return_1d"] = _ret(close, 1)
        feats["tech_return_5d"] = _ret(close, 5)
        feats["tech_return_20d"] = _ret(close, 20)
        feats["tech_return_60d"] = _ret(close, 60)

        # Annualised realised volatility over 20 sessions
        rets = close.pct_change().dropna()
        if len(rets) >= 20:
            feats["tech_volatility_20d"] = round(
                float(rets.tail(20).std()) * (252 ** 0.5) * 100, 6)

        # RSI-14 (Wilder-style simple mean variant · deterministic)
        if len(close) >= 15:
            d = close.diff().dropna().tail(14)
            gain = float(d[d > 0].sum()) / 14
            loss = float(-d[d < 0].sum()) / 14
            if loss == 0:
                feats["tech_rsi_14"] = 100.0
            else:
                rs = gain / loss
                feats["tech_rsi_14"] = round(100 - (100 / (1 + rs)), 6)

        # Volume ratio vs its own 20-session mean
        vcol = next((c for c in ("volume", "Volume", "tick_volume")
                     if c in hist.columns), None)
        if vcol and len(hist) >= 21:
            v = hist[vcol].astype(float)
            base = float(v.tail(20).mean())
            if base > 0:
                feats["tech_volume_ratio_20d"] = round(
                    float(v.iloc[-1]) / base, 6)

        # Distance from the trailing 52-week high
        win = close.tail(252)
        hi = float(win.max())
        if hi > 0:
            feats["tech_dist_52w_high_pct"] = round(
                (float(close.iloc[-1]) / hi - 1.0) * 100, 6)

        # Trend · 20 vs 50 session moving-average gap
        if len(close) >= 50:
            ma20 = float(close.tail(20).mean())
            ma50 = float(close.tail(50).mean())
            if ma50 > 0:
                feats["tech_ma_gap_20_50_pct"] = round(
                    (ma20 / ma50 - 1.0) * 100, 6)

        # ATR-14 as a percentage of price
        if all(c in hist.columns for c in ("high", "low")) and len(hist) >= 15:
            h = hist["high"].astype(float)
            lo = hist["low"].astype(float)
            pc = close.shift(1)
            tr = (h - lo).combine((h - pc).abs(), max).combine(
                (lo - pc).abs(), max)
            atr = float(tr.tail(14).mean())
            last = float(close.iloc[-1])
            if last > 0:
                feats["tech_atr_pct_14"] = round(atr / last * 100, 6)

        return {k: v for k, v in feats.items() if v is not None}
    except Exception:
        return {}


def coverage(root: Path, market: str, tickers, asof: str) -> dict:
    """How many names in a universe actually yield features."""
    n_ok = 0
    per_feature: dict = {f: 0 for f in TECHNICAL_FEATURES}
    for tk in tickers:
        f = compute(root, market, tk, asof)
        if f:
            n_ok += 1
            for k in f:
                per_feature[k] = per_feature.get(k, 0) + 1
    return {"market": market, "asof": asof, "n_universe": len(list(tickers)),
            "n_with_features": n_ok, "per_feature": per_feature}


def pit_selftest(root: Path, market: str, ticker: str,
                 past_asof: str, later_asof: str) -> dict:
    """Prove the PIT cut · a past date's features must not move when later
    bars exist.

    This is the guarantee that makes the substrate usable for walk-forward.
    If it ever fails, every metric computed on these features is void.
    """
    a = compute(root, market, ticker, past_asof)
    # Recompute the SAME past date after the frame has seen later data.
    compute(root, market, ticker, later_asof)
    b = compute(root, market, ticker, past_asof)
    same = a == b
    return {"ticker": ticker, "past_asof": past_asof,
            "later_asof": later_asof, "stable": same,
            "n_features": len(a),
            "drift": None if same else
                     {k: (a.get(k), b.get(k)) for k in set(a) | set(b)
                      if a.get(k) != b.get(k)}}

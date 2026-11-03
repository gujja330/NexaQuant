"""PIE · point-in-time features, each carrying the date it was knowable.

CEO 2026-11-03 · WHY EVERY FEATURE CARRIES A TIMESTAMP
------------------------------------------------------
A backtest that is wrong about what was knowable on a date does not
produce a weaker result, it produces a confident fictional one. So no
feature here is returned as a bare number. Each is a `Feature` carrying
the last bar that fed it, how many bars it used, and whether it was
available at all - and an unavailable feature is ABSENT, never zero.
Zero-filling is what makes a missing input look like a neutral opinion,
which is the same confusion that let three non-signalling models be
counted as dissenting voices in R2's conflict resolver.

THE PIT RULE, STATED ONCE
-------------------------
Every feature on decision date D is computed from bars with index <= D.
Every outcome starts from the first bar strictly AFTER D, because a
decision taken on D cannot transact at D's close. The two windows touch
and never overlap. `asof_bar` on each feature is the evidence that the
first half of that rule held.

WHAT ABSTAINS, AND WHY IT IS NOT A GAP TO BE FILLED
---------------------------------------------------
Sector is empty in both markets (India all None, USA all 'Unknown'), and
there is no point-in-time fundamentals history in this repository. Those
dimensions abstain. Filling them with a universe mean would manufacture
evidence and would raise the measured score of exactly the names we know
least about.

PRIOR EVIDENCE IS THE DANGEROUS ONE
-----------------------------------
A per-ticker historical win rate is the feature most likely to leak,
because the obvious implementation reads the registry as it stands today.
`prior_evidence` therefore counts only episodes CLOSED strictly before D,
and abstains below MIN_PRIOR_EPISODES rather than reporting a win rate
from one trade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Sequence

import pandas as pd

from backend.research.r3_program import outcome_resolver as _res

SCHEMA_VERSION = "1.0.0"

#: Trading days each window needs before it means anything.
MIN_BARS = {
    "ret_20d": 21, "ret_60d": 61, "ret_120d": 121,
    "sma50_ratio": 50, "sma200_ratio": 200, "sma50_over_sma200": 200,
    "vol_20d": 21, "max_dd_60d": 60, "dist_52w_high": 250,
    "liquidity_20d": 20, "rsi_14": 15,
}

#: Below this a per-ticker win rate is an anecdote.
MIN_PRIOR_EPISODES = 3

#: Trading days per year, for annualising realised volatility.
TRADING_DAYS = 252


@dataclass(frozen=True)
class Feature:
    """One measurement, and the proof of when it was knowable."""
    name: str
    value: Optional[float]
    available: bool
    asof_bar: Optional[str]        # last bar date that fed this value
    n_bars_used: int
    source: str
    reason: Optional[str] = None   # why unavailable

    def as_dict(self) -> dict:
        return asdict(self)


def _absent(name: str, reason: str, source: str = "bars") -> Feature:
    return Feature(name=name, value=None, available=False, asof_bar=None,
                   n_bars_used=0, source=source, reason=reason)


def visible_bars(root: Path, market: str, ticker: str,
                 asof: str) -> Optional[pd.DataFrame]:
    """Bars with index <= asof · the only frame a decision on asof may see.

    `tail()` is deliberately not applied before this cut. Taking a tail of
    the full frame and then cutting to asof is what reduced historical
    windows to zero bars in the R3 waves; cutting first and then taking a
    window is the order that survives a historical date.
    """
    bars = _res._bars(Path(root), str(market).lower(), ticker)
    if bars is None or not asof:
        return None
    w = bars[bars.index <= pd.Timestamp(str(asof)[:10])]
    return None if w.empty else w


def _ret(w: pd.DataFrame, n: int, name: str) -> Feature:
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    a = float(w["close"].iloc[-(n + 1)])
    b = float(w["close"].iloc[-1])
    if a <= 0:
        return _absent(name, "NON_POSITIVE_BASE")
    return Feature(name, 100.0 * (b - a) / a, True,
                   str(w.index[-1].date()), n + 1, "bars")


def _sma_ratio(w: pd.DataFrame, n: int, name: str) -> Feature:
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    sma = float(w["close"].iloc[-n:].mean())
    last = float(w["close"].iloc[-1])
    if sma <= 0:
        return _absent(name, "NON_POSITIVE_SMA")
    return Feature(name, 100.0 * (last - sma) / sma, True,
                   str(w.index[-1].date()), n, "bars")


def _sma_cross(w: pd.DataFrame) -> Feature:
    name = "sma50_over_sma200"
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    f = float(w["close"].iloc[-50:].mean())
    s = float(w["close"].iloc[-200:].mean())
    if s <= 0:
        return _absent(name, "NON_POSITIVE_SMA")
    return Feature(name, 100.0 * (f - s) / s, True,
                   str(w.index[-1].date()), 200, "bars")


def _vol(w: pd.DataFrame) -> Feature:
    name = "vol_20d"
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    r = w["close"].iloc[-21:].pct_change().dropna()
    if len(r) < 2:
        return _absent(name, "NO_RETURNS")
    return Feature(name, float(r.std() * math.sqrt(TRADING_DAYS) * 100.0), True,
                   str(w.index[-1].date()), 21, "bars")


def _max_dd(w: pd.DataFrame) -> Feature:
    name = "max_dd_60d"
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    c = w["close"].iloc[-60:]
    peak = c.cummax()
    dd = ((c - peak) / peak).min()
    return Feature(name, float(dd) * 100.0, True,
                   str(w.index[-1].date()), 60, "bars")


def _dist_high(w: pd.DataFrame) -> Feature:
    name = "dist_52w_high"
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    c = w["close"].iloc[-250:]
    hi = float(c.max())
    if hi <= 0:
        return _absent(name, "NON_POSITIVE_HIGH")
    return Feature(name, 100.0 * (float(c.iloc[-1]) - hi) / hi, True,
                   str(w.index[-1].date()), 250, "bars")


def _liquidity(w: pd.DataFrame) -> Feature:
    name = "liquidity_20d"
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    vcol = "tick_volume" if "tick_volume" in w.columns else (
        "volume" if "volume" in w.columns else None)
    if vcol is None:
        return _absent(name, "NO_VOLUME_COLUMN")
    turn = (w["close"].iloc[-20:] * w[vcol].iloc[-20:]).median()
    if not (turn == turn) or turn <= 0:
        return _absent(name, "NON_POSITIVE_TURNOVER")
    return Feature(name, float(math.log10(float(turn))), True,
                   str(w.index[-1].date()), 20, "bars")


def _rsi(w: pd.DataFrame) -> Feature:
    name = "rsi_14"
    need = MIN_BARS[name]
    if len(w) < need:
        return _absent(name, "NEEDS_%d_BARS_HAS_%d" % (need, len(w)))
    d = w["close"].iloc[-15:].diff().dropna()
    up = d.clip(lower=0).mean()
    dn = (-d.clip(upper=0)).mean()
    if dn == 0:
        return Feature(name, 100.0, True, str(w.index[-1].date()), 15, "bars")
    rs = float(up / dn)
    return Feature(name, 100.0 - 100.0 / (1.0 + rs), True,
                   str(w.index[-1].date()), 15, "bars")


def bar_features(root: Path, market: str, ticker: str,
                 asof: str) -> Dict[str, Feature]:
    """Every bar-derived feature for one (ticker, asof), PIT-correct."""
    w = visible_bars(root, market, ticker, asof)
    names = list(MIN_BARS)
    if w is None:
        return {n: _absent(n, "NO_BARS_ON_OR_BEFORE_ASOF") for n in names}
    out = {
        "ret_20d": _ret(w, 20, "ret_20d"),
        "ret_60d": _ret(w, 60, "ret_60d"),
        "ret_120d": _ret(w, 120, "ret_120d"),
        "sma50_ratio": _sma_ratio(w, 50, "sma50_ratio"),
        "sma200_ratio": _sma_ratio(w, 200, "sma200_ratio"),
        "sma50_over_sma200": _sma_cross(w),
        "vol_20d": _vol(w),
        "max_dd_60d": _max_dd(w),
        "dist_52w_high": _dist_high(w),
        "liquidity_20d": _liquidity(w),
        "rsi_14": _rsi(w),
    }
    return out


def prior_evidence(episodes: pd.DataFrame, ticker: str,
                   asof: str) -> Dict[str, Feature]:
    """Per-ticker registry evidence from episodes CLOSED strictly before asof.

    `closed_date < asof`, not `<=`: an episode closing on the decision date
    is not a settled fact at the moment the decision is taken, and the
    difference is exactly the kind of one-day leak that flatters a result.
    """
    src = "registry(closed<asof)"
    names = ("prior_n", "prior_win_rate", "prior_mean_ret")
    if episodes is None or episodes.empty or not asof:
        return {n: _absent(n, "NO_EPISODES", src) for n in names}
    d = pd.Timestamp(str(asof)[:10])
    cd = pd.to_datetime(episodes["closed_date"], errors="coerce")
    m = (episodes["ticker"].astype(str).str.upper() == str(ticker).upper())
    hist = episodes[m & cd.notna() & (cd < d)]
    hist = hist[hist["registry_realized_resolved"].astype(bool)]
    n = int(len(hist))
    if n < MIN_PRIOR_EPISODES:
        r = "ONLY_%d_PRIOR_EPISODES_NEED_%d" % (n, MIN_PRIOR_EPISODES)
        return {k: _absent(k, r, src) for k in names}
    pnl = pd.to_numeric(hist["registry_realized_pct"], errors="coerce").dropna()
    if pnl.empty:
        return {k: _absent(k, "NO_RESOLVED_RETURNS", src) for k in names}
    last = str(cd[hist.index].max().date())
    return {
        "prior_n": Feature("prior_n", float(n), True, last, n, src),
        "prior_win_rate": Feature("prior_win_rate",
                                  100.0 * float((pnl > 0).mean()), True,
                                  last, n, src),
        "prior_mean_ret": Feature("prior_mean_ret", float(pnl.mean()), True,
                                  last, n, src),
    }


#: Dimensions with no point-in-time evidence anywhere in this repository.
#: Listed explicitly so the abstention is a declared position rather than
#: a silent omission a later reader mistakes for an oversight.
STRUCTURAL_ABSTENTIONS = {
    "sector": "SECTOR_EMPTY_IN_BOTH_MARKETS",
    "fundamentals": "NO_POINT_IN_TIME_FUNDAMENTALS_HISTORY",
}


def structural_abstentions() -> Dict[str, Feature]:
    return {k: _absent(k, v, "none") for k, v in STRUCTURAL_ABSTENTIONS.items()}


def all_features(root: Path, market: str, ticker: str, asof: str,
                 episodes: Optional[pd.DataFrame] = None) -> Dict[str, Feature]:
    out: Dict[str, Feature] = {}
    out.update(bar_features(root, market, ticker, asof))
    out.update(prior_evidence(episodes if episodes is not None
                              else pd.DataFrame(), ticker, asof))
    out.update(structural_abstentions())
    return out


def availability(features: Dict[str, Feature]) -> dict:
    av = {k: v.available for k, v in features.items()}
    return {
        "n_features": len(av),
        "n_available": sum(1 for v in av.values() if v),
        "available": sorted(k for k, v in av.items() if v),
        "unavailable": {k: features[k].reason
                        for k, v in av.items() if not v},
        "max_asof_bar": max((f.asof_bar for f in features.values()
                             if f.asof_bar), default=None),
    }


def assert_no_lookahead(features: Dict[str, Feature], asof: str) -> None:
    """No feature may carry evidence dated after the decision.

    Called by the backtest on every row rather than spot-checked, because
    a leak that appears on 1 of 247 rows is still a leak and is exactly
    the one a sampled audit misses.
    """
    d = pd.Timestamp(str(asof)[:10])
    for k, f in features.items():
        if f.asof_bar and pd.Timestamp(f.asof_bar) > d:
            raise AssertionError(
                "LOOKAHEAD: feature %r carries evidence dated %s for a "
                "decision on %s" % (k, f.asof_bar, asof))

"""R3 AI DISCOVERY LAB v1 — latent structure, not another hand-made feature.

THE CHANGE OF STANCE
--------------------
Every prior wave asked "does feature X predict return?", tested it, and rejected
it. This module asks a different question: are there recurring STATES, shapes
and relationships in the data that feature-by-feature testing cannot see?

THE SUBSTRATE, AND THE ONE DISTINCTION THAT MATTERS
---------------------------------------------------
Two very different depths live in this repo and must never be blurred:

  PRICE HISTORY      India 230 tickers from 2020-06-18, USA 900 from 2021-08-06.
                     ~1,568 and ~1,257 trading dates. This is real depth, and it
                     is what archetypes, latent states, the relational graph and
                     analogue search actually run on.

  SEALED R2 MEMORY   three dates. Anything involving R2's own confidence,
                     decisions or entries is bounded by that, no matter how much
                     price history sits underneath it.

So a discovery about trajectory shape can carry hundreds of date units, while a
discovery about R2 behaviour in that shape carries three. Both are reported,
with their own date depth attached, and the deep one is never allowed to lend
its credibility to the shallow one.

SURVIVORSHIP
------------
The ticker files are the names that exist TODAY. Anything delisted mid-history
is absent, which biases every long-horizon statistic here upward. USA carries
908 bar files against a 516-name index, so several hundred non-index names are
present and the bias is partially mitigated; India's 230 files are close to its
228-name universe, so India is materially more exposed. This is recorded on
every discovery rather than mentioned once and forgotten.

PIT
---
Features at date d use bars up to and including d. Forward outcomes carry their
own outcome_date. Analogue search excludes the query ticker and any reference
date inside an embargo window. Bars are read directly from the parquets, NOT
through `adapt_prices`, whose tail-before-cutoff defect (CANON-2) would silently
shrink every historical window to nothing.

GOVERNANCE
----------
Research only. No production write, no R2 change, no promotion. The strongest
possible outcome of this module is CANDIDATE_FOR_CONFIRMATORY_VALIDATION.
"""
from __future__ import annotations

import glob
import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

SCHEMA_VERSION = "aegis.r3.discovery_lab.v1"
SEED = 20260916

BARS_GLOB = {"india": "data/raw/india/*_D1.parquet",
             "usa": "usa/data/raw/us/*_D1.parquet"}

WINDOW = 60          # trajectory lookback
SHAPE_POINTS = 12    # resampled path points
FWD = (1, 5, 10, 20)
EMBARGO_DAYS = 5     # §7 governance: analogue references must clear this
MIN_BARS = 250


# ── DISCOVERY LEDGER (§15) ────────────────────────────────────────────
@dataclass
class Discovery:
    """One entry. Discovery and confirmation are deliberately separate fields:
    exploring widely is fine, provided nothing exploratory is ever counted as
    confirmatory evidence."""
    discovery_id: str
    method: str
    market: str
    dataset: str
    date_range: str
    n_rows: int
    n_tickers: int
    n_dates: int
    features: list
    representation: str
    seed: int
    trial_count: int
    hypothesis: str
    stage: str = "DISCOVERY"          # never CONFIRMATORY in this module
    test: Optional[str] = None
    result: Optional[dict] = None
    oos_status: str = "NOT_ATTEMPTED"
    adversarial: Optional[dict] = None
    survivorship_exposure: str = "PRESENT"
    disposition: str = "CANDIDATE_FOR_CONFIRMATORY_VALIDATION"
    notes: str = ""


class Ledger:
    def __init__(self) -> None:
        self.items: list[Discovery] = []

    def add(self, d: Discovery) -> Discovery:
        self.items.append(d)
        return d

    def dump(self) -> list[dict]:
        return [asdict(d) for d in self.items]


# ── PANEL ─────────────────────────────────────────────────────────────
def _read_bars(path: str) -> Optional[pd.DataFrame]:
    try:
        d = pd.read_parquet(path)
    except Exception:
        return None
    if d.empty or len(d) < MIN_BARS:
        return None
    d.index = pd.to_datetime(d.index)
    d = d.sort_index()
    d.columns = [c.lower() for c in d.columns]
    if "volume" not in d.columns and "tick_volume" in d.columns:
        d["volume"] = d["tick_volume"]
    need = {"open", "high", "low", "close"}
    if not need <= set(d.columns):
        return None
    return d


def _ticker_panel(t: str, d: pd.DataFrame, stride: int) -> Optional[pd.DataFrame]:
    """Scale-free trajectory state at each sampled date, plus forward outcomes.

    Everything here is computed from a trailing window. `shift` is used wherever
    a rolling statistic would otherwise include the current bar in a way that a
    live caller could not have known.
    """
    c = d["close"].astype(float)
    if c.le(0).any():
        c = c.where(c > 0)
    lr = np.log(c).diff()

    f = pd.DataFrame(index=d.index)
    for w in (1, 5, 10, 20, 60):
        f["ret_%dd" % w] = c.pct_change(w) * 100.0
    f["vol_20"] = lr.rolling(20).std() * np.sqrt(252) * 100.0
    f["vol_60"] = lr.rolling(60).std() * np.sqrt(252) * 100.0
    f["vol_ratio"] = f["vol_20"] / f["vol_60"]
    roll_max = c.rolling(WINDOW).max()
    roll_min = c.rolling(WINDOW).min()
    f["dd_60"] = 100.0 * (c - roll_max) / roll_max
    rng = (roll_max - roll_min)
    f["pos_60"] = 100.0 * (c - roll_min) / rng.where(rng > 0)
    f["skew_20"] = lr.rolling(20).skew()
    f["kurt_20"] = lr.rolling(20).kurt()
    # normalised trend slope over 20d
    x = np.arange(20)
    xm = x.mean()
    denom = ((x - xm) ** 2).sum()
    f["slope_20"] = (c.rolling(20).apply(
        lambda y: float(((x - xm) * (y - y.mean())).sum() / denom / (y.mean() or np.nan)),
        raw=True) * 100.0)
    v = d["volume"].astype(float)
    f["vol_ratio_5v20"] = v.rolling(5).mean() / v.rolling(20).mean().replace(0, np.nan)

    # forward outcomes, each with its own outcome date
    out = pd.DataFrame(index=d.index)
    for h in FWD:
        out["fwd_%dd" % h] = (c.shift(-h) / c - 1.0) * 100.0
        out["fwd_%dd_date" % h] = pd.Series(d.index, index=d.index).shift(-h)
    fwd_lo = d["low"].astype(float).shift(-1).rolling(20).min().shift(-19)
    fwd_hi = d["high"].astype(float).shift(-1).rolling(20).max().shift(-19)
    out["fwd_mae_20"] = 100.0 * (fwd_lo - c) / c
    out["fwd_mfe_20"] = 100.0 * (fwd_hi - c) / c

    p = pd.concat([f, out], axis=1)
    p["ticker"] = t
    p["date"] = d.index
    p = p.iloc[WINDOW:]                       # need a full trailing window
    if stride > 1:
        p = p.iloc[::stride]
    p = p.dropna(subset=["ret_20d", "vol_20", "dd_60", "pos_60"])
    return p if len(p) else None


def _shapes(t: str, d: pd.DataFrame, dates: pd.DatetimeIndex) -> np.ndarray:
    """Normalised cumulative-return path over the trailing window.

    Each path is demeaned and scaled by its own dispersion, so clustering finds
    SHAPE rather than magnitude - otherwise every high-volatility name lands in
    the same cluster and the 'archetype' is just volatility with extra steps.
    """
    c = d["close"].astype(float)
    pos = {dt: i for i, dt in enumerate(d.index)}
    idx = np.linspace(0, WINDOW - 1, SHAPE_POINTS).round().astype(int)
    rows = []
    for dt in dates:
        i = pos.get(dt)
        if i is None or i < WINDOW:
            rows.append(np.full(SHAPE_POINTS, np.nan))
            continue
        w = c.iloc[i - WINDOW + 1: i + 1].to_numpy(dtype=float)
        base = w[0]
        if not np.isfinite(base) or base <= 0:
            rows.append(np.full(SHAPE_POINTS, np.nan))
            continue
        path = (w / base - 1.0) * 100.0
        s = np.nanstd(path)
        path = (path - np.nanmean(path)) / (s if s > 1e-9 else 1.0)
        rows.append(path[idx])
    return np.asarray(rows, dtype=float)


def build_panel(root: Path, market: str, stride: int = 5,
                max_tickers: Optional[int] = None) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """The lab substrate: one trajectory state per (ticker, sampled date)."""
    root = Path(root)
    files = sorted(glob.glob(str(root / BARS_GLOB[market])))
    if max_tickers:
        files = files[:max_tickers]
    frames, shapes, kept = [], [], 0
    for fp in files:
        t = Path(fp).stem.replace("_D1", "").lstrip("_").upper()
        d = _read_bars(fp)
        if d is None:
            continue
        p = _ticker_panel(t, d, stride)
        if p is None:
            continue
        s = _shapes(t, d, pd.DatetimeIndex(p["date"]))
        frames.append(p)
        shapes.append(s)
        kept += 1
    if not frames:
        return pd.DataFrame(), np.empty((0, SHAPE_POINTS)), {"tickers": 0}
    panel = pd.concat(frames, ignore_index=True)
    shape = np.vstack(shapes)
    ok = np.isfinite(shape).all(axis=1)
    panel, shape = panel.loc[ok].reset_index(drop=True), shape[ok]
    meta = {
        "market": market, "tickers": kept, "rows": int(len(panel)),
        "dates": int(panel["date"].nunique()),
        "date_min": str(panel["date"].min().date()),
        "date_max": str(panel["date"].max().date()),
        "stride_trading_days": stride, "window": WINDOW,
        "shape_points": SHAPE_POINTS,
        "survivorship": ("ticker files are TODAY's names; delisted names absent, "
                         "which biases long-horizon statistics upward"),
    }
    return panel, shape, meta


def panel_hash(panel: pd.DataFrame) -> str:
    """Reproducibility metadata (§21)."""
    if panel.empty:
        return ""
    key = "%s|%s|%d|%d" % (panel["date"].min(), panel["date"].max(),
                           len(panel), panel["ticker"].nunique())
    return hashlib.sha256(key.encode()).hexdigest()[:16]

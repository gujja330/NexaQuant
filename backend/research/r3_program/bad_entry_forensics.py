"""R3 BAD-ENTRY / SEVERE-LOSS FORENSICS.

THE QUESTION
------------
Not "why did AEGIS pick bad stocks" but:

    was the failure already detectable AT ENTRY, using only information
    available at the entry timestamp?

THE SPLIT THAT MATTERS
----------------------
A position that goes straight down and never produces a meaningful favourable
excursion is a different failure from one that runs +8% and gives it back.

    near-zero MFE, deep MAE      -> ENTRY quality is the candidate
    strong MFE, then reversal    -> EXIT / holding policy is the candidate

Collapsing both into "bad stock" hides the mechanism, so the MAE/MFE split runs
before any taxonomy is applied.

WHAT THIS MODULE IS NOT
-----------------------
It writes nothing to production and trains no model. Every output lands under
reports/research/r3/. R3 production writes remain 0.

A WARNING THE DATA ITSELF CARRIES
---------------------------------
86 R2 positions in this book arrive through 9 admission DATES; 32 of 54 open
positions entered on 2026-09-09 alone. Rows are not independent units. Any
statistic here is descriptive unless it survives date-aware testing, and with
9 effective units most cannot.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.bad_entry_forensics.v1"

# MFE below this never counted as a real chance to exit in profit.
MEANINGFUL_MFE_PCT = 2.0
# The severe-loss definition already pre-registered by the evidence engine.
SEVERE_LOSS_PCT = -5.0

BARS = {"india": "data/raw/india/%s_D1.parquet",
        "usa": "usa/data/raw/us/%s_D1.parquet"}

_BAR_CACHE: dict = {}


def _bars(root: Path, market: str, ticker: str) -> Optional[pd.DataFrame]:
    key = (market, ticker)
    if key in _BAR_CACHE:
        return _BAR_CACHE[key]
    t = str(ticker).upper().replace(".NS", "").replace(".BO", "")
    p = root / (BARS[market] % t)
    d = None
    if p.exists():
        try:
            d = pd.read_parquet(p)
            d.index = pd.to_datetime(d.index)
            d = d.sort_index()
        except Exception:
            d = None
    _BAR_CACHE[key] = d
    return d


@dataclass
class EntryRecord:
    market: str
    ticker: str
    entry_date: str
    entry_price: Optional[float]
    entry_confidence: Optional[float]
    sector: Optional[str]
    engine: Optional[str]
    status: str                      # OPEN | CLOSED
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None
    realized_pnl_pct: Optional[float] = None
    holding_days: Optional[int] = None
    stop: Optional[float] = None
    # forward path
    fwd1d: Optional[float] = None
    fwd3d: Optional[float] = None
    fwd5d: Optional[float] = None
    fwd10d: Optional[float] = None
    fwd20d: Optional[float] = None
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    days_to_mae: Optional[int] = None
    days_to_mfe: Optional[int] = None
    n_fwd_bars: int = 0
    # classification
    never_profitable: Optional[int] = None
    profit_then_reversal: Optional[int] = None
    severe_loss: Optional[int] = None


def _forward_path(root: Path, market: str, ticker: str, entry_date: str,
                  entry_price: Optional[float], horizon: int = 60) -> dict:
    """MAE/MFE and forward returns measured strictly AFTER the entry date."""
    out: dict = {"n_fwd_bars": 0}
    b = _bars(root, market, ticker)
    if b is None or not entry_date:
        return out
    a = pd.Timestamp(entry_date)
    at, fut = b[b.index <= a], b[b.index > a]
    if fut.empty:
        return out
    p0 = float(entry_price) if entry_price else (
        float(at["close"].iloc[-1]) if not at.empty else None)
    if not p0:
        return out
    w = fut.iloc[:horizon]
    out["n_fwd_bars"] = len(fut)
    for lbl, n in (("fwd1d", 1), ("fwd3d", 3), ("fwd5d", 5),
                   ("fwd10d", 10), ("fwd20d", 20)):
        out[lbl] = (100 * (float(fut["close"].iloc[n - 1]) - p0) / p0) if len(fut) >= n else None
    lo, hi = w["low"], w["high"]
    if len(w):
        out["mae_pct"] = 100 * (float(lo.min()) - p0) / p0
        out["mfe_pct"] = 100 * (float(hi.max()) - p0) / p0
        out["days_to_mae"] = int(lo.reset_index(drop=True).idxmin()) + 1
        out["days_to_mfe"] = int(hi.reset_index(drop=True).idxmax()) + 1
    return out


def build(root: Path, market: str) -> pd.DataFrame:
    """One row per historical R2 entry, open and closed."""
    root = Path(root)
    lc = root / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    if not lc.exists():
        return pd.DataFrame()
    d = json.loads(lc.read_text(encoding="utf-8"))

    recs: list[EntryRecord] = []
    for c in d.get("current", []):
        if not str(c.get("engine", "")).upper().startswith("R2"):
            continue
        recs.append(EntryRecord(
            market=market, ticker=c["ticker"], entry_date=c.get("entry_date"),
            entry_price=c.get("entry_price"), entry_confidence=c.get("confidence_pct"),
            sector=c.get("sector"), engine=c.get("engine"), status="OPEN",
            holding_days=c.get("holding_days"), stop=c.get("stop")))
    for e in d.get("exits", []):
        if e.get("record_type") != "REALIZED EXIT":
            continue
        recs.append(EntryRecord(
            market=market, ticker=e["ticker"], entry_date=e.get("entry_date"),
            entry_price=e.get("entry_price"),
            entry_confidence=e.get("entry_confidence_pct"),
            sector=e.get("sector"), engine=e.get("engine"), status="CLOSED",
            exit_date=e.get("exit_date"), exit_reason=e.get("exit_reason"),
            realized_pnl_pct=e.get("realized_pnl_pct"),
            holding_days=e.get("holding_days"), stop=e.get("stop")))

    rows = []
    for r in recs:
        path = _forward_path(root, market, r.ticker, r.entry_date, r.entry_price)
        for k, v in path.items():
            setattr(r, k, v)
        # ── the split that matters ──────────────────────────────────
        # "Never profitable" is about OPPORTUNITY, not outcome: did the
        # position ever offer a meaningful chance to leave in profit?
        if r.mfe_pct is not None:
            r.never_profitable = 1 if r.mfe_pct < MEANINGFUL_MFE_PCT else 0
            worst = r.realized_pnl_pct if r.realized_pnl_pct is not None else r.mae_pct
            r.profit_then_reversal = 1 if (
                r.mfe_pct >= MEANINGFUL_MFE_PCT and worst is not None
                and worst <= SEVERE_LOSS_PCT) else 0
        outcome = r.realized_pnl_pct if r.realized_pnl_pct is not None else r.fwd10d
        if outcome is not None:
            r.severe_loss = 1 if outcome <= SEVERE_LOSS_PCT else 0
        rows.append(asdict(r))
    return pd.DataFrame(rows)


def taxonomy(df: pd.DataFrame) -> pd.DataFrame:
    """Descriptive labels. A trade may carry several - the mandate forbids
    forcing one explanation."""
    if df.empty:
        return df
    t = df.copy()
    t["F1_IMMEDIATE_ADVERSE"] = ((t["fwd3d"].notna()) & (t["fwd3d"] <= -2.0)).astype(int)
    t["F2_NEVER_PROFITABLE"] = t["never_profitable"].fillna(0).astype(int)
    t["F3_PROFIT_THEN_REVERSAL"] = t["profit_then_reversal"].fillna(0).astype(int)
    t["F7_LOW_CONFIDENCE"] = (
        (t["entry_confidence"].notna()) & (t["entry_confidence"] < 40)).astype(int)
    t["F9_STOP_DISTANCE"] = (
        (t["mae_pct"].notna()) & (t["mae_pct"] <= -8.0)).astype(int)
    t["F10_HORIZON"] = t["exit_reason"].fillna("").str.contains(
        "horizon", case=False).astype(int)
    # F11 is a PORTFOLIO property, not a per-trade one: entries sharing an
    # admission date are one bet however many tickers they wear.
    cnt = t.groupby("entry_date")["ticker"].transform("count")
    t["F11_CORRELATED_EXPOSURE"] = (cnt >= 5).astype(int)
    return t

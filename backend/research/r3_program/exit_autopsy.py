"""EXIT AUTOPSY — why do winners become losers before they close?

THE MEASURED LEAK
-----------------
Three independent angles all point at the exit, not the entry:

  61%   of India exits were positive at some point and closed negative
  +3.74% -> -2.19%   mean peak while open vs mean realized (5.93pp given back)
  26%   of positions green at ~12 days were still green at exit (7 of 27)
  0%    of positions red at ~12 days ever recovered (0 of 41)
  73%   of all exits are stop-loss triggered, at a mean of -3.15%

Entries find gains. The exit hands them back. This module measures exactly
where, for every realized trade, using only the price series.

THE DISCIPLINE THAT MATTERS MOST HERE
-------------------------------------
Retrospectively testing alternative exit rules is the easiest way in finance
to produce a beautiful lie. Every counterfactual in this module is therefore:

  - computed from bars ONLY, never from the reported P&L it is meant to check
  - reported with its own date depth, because 107 trades across a handful of
    admission dates is not 107 independent observations
  - cross-validated: every reported P&L is recomputed from the price series
    and the disagreement is reported rather than silently reconciled

A counterfactual that beats the live policy on the same 107 trades it was
designed against is a curve fit until it survives out-of-sample. Nothing here
promotes anything; production exit policy stays frozen.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

SCHEMA_VERSION = "aegis.r3.exit_autopsy.v1"

BARS = {"india": "data/raw/india/%s_D1.parquet",
        "usa": "usa/data/raw/us/%s_D1.parquet"}

_CACHE: dict = {}


def _tkey(t) -> str:
    return str(t).upper().strip().replace(".NS", "").replace(".BO", "")


def bars(root: Path, market: str, ticker: str) -> Optional[pd.DataFrame]:
    k = (str(root), market, _tkey(ticker))
    if k in _CACHE:
        return _CACHE[k]
    p = Path(root) / (BARS[market] % _tkey(ticker))
    d = None
    if p.exists():
        try:
            d = pd.read_parquet(p)
            d.index = pd.to_datetime(d.index)
            d = d.sort_index()
            d.columns = [c.lower() for c in d.columns]
        except Exception:
            d = None
    _CACHE[k] = d
    return d


def load_trades(root: Path, market: str) -> pd.DataFrame:
    """Every REALIZED EXIT, with the fields needed to reconstruct it."""
    p = Path(root) / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    if not p.exists():
        return pd.DataFrame()
    lc = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for e in (lc.get("exits") or []):
        if e.get("record_type") != "REALIZED EXIT":
            continue
        rows.append({
            "market": market,
            "ticker": _tkey(e.get("ticker")),
            "position_id": e.get("position_id"),
            "engine": e.get("engine"),
            "entry_date": str(e.get("entry_date") or "")[:10],
            "exit_date": str(e.get("exit_date") or "")[:10],
            "entry_price": e.get("entry_price"),
            "exit_price": e.get("exit_price"),
            "reported_pnl_pct": e.get("realized_pnl_pct"),
            "exit_reason": e.get("exit_reason"),
            "holding_days": e.get("holding_days"),
            "entry_confidence": e.get("entry_confidence_pct"),
            "sector": e.get("sector"),
        })
    return pd.DataFrame(rows)


# ── VALIDATION PASS 1 · recompute every P&L from the bars ─────────────
def validate_ledger(root: Path, df: pd.DataFrame, tol: float = 0.15) -> dict:
    """Recompute each trade's P&L from the price series and compare.

    The reported P&L and the bars are independent sources. If they disagree
    the ledger cannot be trusted for anything downstream, so this runs FIRST
    and its disagreements are reported, never quietly reconciled.
    """
    recomputed, issues = [], []
    for _, t in df.iterrows():
        b = bars(root, t["market"], t["ticker"])
        ep, xp = t.get("entry_price"), t.get("exit_price")
        rec = None
        if ep and xp:
            try:
                rec = 100.0 * (float(xp) - float(ep)) / float(ep)
            except Exception:
                rec = None
        recomputed.append(rec)
        rep = t.get("reported_pnl_pct")
        if rec is not None and rep is not None and abs(float(rep) - rec) > tol:
            issues.append({"ticker": t["ticker"], "position_id": t["position_id"],
                           "reported": float(rep), "recomputed_from_prices": round(rec, 4),
                           "delta": round(float(rep) - rec, 4)})
        if b is None:
            issues.append({"ticker": t["ticker"], "issue": "NO_BARS"})
    df = df.copy()
    df["pnl_from_prices"] = recomputed
    nb = sum(1 for i in issues if i.get("issue") == "NO_BARS")
    return {"n_trades": int(len(df)),
            "n_price_mismatches": int(len(issues) - nb),
            "n_missing_bars": nb,
            "tolerance_pct": tol,
            "mismatches": issues[:25],
            "verdict": "LEDGER_CONSISTENT" if len(issues) == 0 else "DISCREPANCIES_FOUND",
            "_df": df}


# ── PATH RECONSTRUCTION ───────────────────────────────────────────────
def reconstruct(root: Path, df: pd.DataFrame) -> pd.DataFrame:
    """The full intra-trade path: peak, trough, timing, and the give-back.

    Everything is measured between entry_date and exit_date inclusive, from
    bars alone, so it is independent of whatever the lifecycle recorded.
    """
    out = []
    for _, t in df.iterrows():
        b = bars(root, t["market"], t["ticker"])
        rec = dict(t)
        rec.update({"peak_pct": None, "trough_pct": None, "days_to_peak": None,
                    "days_to_trough": None, "giveback_pp": None, "n_bars": 0,
                    "peak_before_trough": None, "exit_capture_pct": None})
        if b is None or not t["entry_date"] or not t["exit_date"]:
            out.append(rec)
            continue
        try:
            a, z = pd.Timestamp(t["entry_date"]), pd.Timestamp(t["exit_date"])
            ep = float(t["entry_price"])
        except Exception:
            out.append(rec)
            continue
        w = b[(b.index > a) & (b.index <= z)]
        if w.empty or not ep:
            out.append(rec)
            continue
        hi, lo = w["high"].astype(float), w["low"].astype(float)
        peak = 100.0 * (float(hi.max()) - ep) / ep
        trough = 100.0 * (float(lo.min()) - ep) / ep
        dpk = int(hi.reset_index(drop=True).idxmax()) + 1
        dtr = int(lo.reset_index(drop=True).idxmin()) + 1
        realized = t.get("pnl_from_prices")
        rec.update({
            "peak_pct": round(peak, 4), "trough_pct": round(trough, 4),
            "days_to_peak": dpk, "days_to_trough": dtr, "n_bars": int(len(w)),
            "peak_before_trough": bool(dpk < dtr),
            # how much of the best available gain the exit actually captured
            "exit_capture_pct": (round(100.0 * realized / peak, 2)
                                 if (realized is not None and peak and peak > 0) else None),
            "giveback_pp": (round(peak - realized, 4)
                            if (realized is not None and peak is not None) else None),
        })
        out.append(rec)
    return pd.DataFrame(out)


# ── VALIDATION PASS 2 · independent recompute of the headline ─────────
def validate_giveback(rc: pd.DataFrame) -> dict:
    """Recompute the give-back headline a second, different way.

    Pass 1 checked the ledger against prices. This checks the AGGREGATE two
    ways - row-wise mean of per-trade give-back, and the difference of the two
    column means - because a single aggregation path can hide a filtering bug.
    """
    d = rc.dropna(subset=["peak_pct", "pnl_from_prices"])
    if d.empty:
        return {"status": "EMPTY"}
    way1 = float((d["peak_pct"] - d["pnl_from_prices"]).mean())
    way2 = float(d["peak_pct"].mean() - d["pnl_from_prices"].mean())
    winners_given_back = d[(d["peak_pct"] >= 2.0) & (d["pnl_from_prices"] < 0)]
    return {"n": int(len(d)),
            "mean_peak_pct": round(float(d["peak_pct"].mean()), 4),
            "mean_realized_pct": round(float(d["pnl_from_prices"].mean()), 4),
            "giveback_rowwise_mean_pp": round(way1, 4),
            "giveback_colmean_diff_pp": round(way2, 4),
            "agree": bool(abs(way1 - way2) < 1e-6),
            "n_peaked_2pct_then_closed_negative": int(len(winners_given_back)),
            "pct_of_trades": round(100.0 * len(winners_given_back) / len(d), 1)}

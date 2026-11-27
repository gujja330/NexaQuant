"""Exit rule robustness across regimes · research only, both markets.

CEO 2026-11-26: "we need to research on this, we cannot take blind action".

WHY
---
The AEGIS replay can only use AEGIS's own positions - about 20 USA entry
dates since August - and on that evidence "book half + let half run" beat
"book all at target" in only 1 of 5 date blocks. That is too thin to choose
on. This study tests the same exit rules on every stock in the universe,
with an entry every STEP trading days across the full price history (5-6
years), which yields well over 100 independent entry dates per market and
spans trending and choppy regimes.

WHAT IT TESTS, AND WHAT IT DOES NOT
-----------------------------------
It tests the EXIT RULES - do they protect the downside, do they capture
trends, does that depend on the regime - on entries that are not AEGIS's
picks. It does not prove the rules on AEGIS's own selection; the replay
(exit_policy_replay.py) remains the check for that. A MOMENTUM subset
(63-day return > 0 at entry) approximates what R2 tends to buy.

POINT IN TIME
-------------
Volatility, ATR, the 200-day average and market breadth are rolling values
computed only from bars up to the entry bar.

PRE-REGISTERED DECISION (fixed before the results were seen)
------------------------------------------------------------
SPLIT is preferred to BOOK_ALL only if it wins on more than half of entry
dates in BOTH the trending and the choppy regime, with severe-loss rate and
worst loss no worse. Otherwise BOOK_ALL stands.
"""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from backend.research import exit_policy_replay as R

STEP = 10                 # trading days between entries per ticker
HISTORY = 200             # bars required before an entry (for the 200-day mean)
FORWARD = 60              # bars simulated after entry
BREADTH_TREND = 0.60      # >= : broad uptrend
BREADTH_DOWN = 0.40       # <  : broad downtrend ; between = CHOP

POLICIES = {
    "BOOK_ALL": {"kind": "TB", "h": 10, "k_tp": 1.0, "k_sl": 1.0},
    "RUN_ALL": {"kind": "TB_RUN", "h": 10, "k_tp": 1.0, "k_sl": 1.0,
                "k_trail": 2.0, "h_max": 30},
}


def _bars_dir(root: Path, market: str) -> Path:
    return Path(root) / ("usa/data/raw/us" if market == "usa" else "data/raw/india")


def load_universe(root: Path, market: str) -> dict:
    out = {}
    for p in sorted(_bars_dir(root, market).glob("*_D1.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        df.columns = [str(c).lower() for c in df.columns]
        if not {"open", "high", "low", "close"} <= set(df.columns) or len(df) < HISTORY + 20:
            continue
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        df = df[~df.index.duplicated(keep="last")].sort_index()
        c = df["close"].astype(float)
        lr = np.log(c / c.shift(1))
        prev = c.shift(1)
        tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                        (df["low"] - prev).abs()], axis=1).max(axis=1)
        df["sigma"] = lr.rolling(20).std()            # past-only windows
        df["atr"] = tr.rolling(14).mean()
        df["sma200"] = c.rolling(200).mean()
        df["mom63"] = c / c.shift(63) - 1
        out[p.stem.replace("_D1", "")] = df
    return out


def breadth_by_date(universe: dict) -> dict:
    above, total = defaultdict(int), defaultdict(int)
    for df in universe.values():
        ok = df["sma200"].notna()
        for d, a in zip(df.index[ok], (df["close"] > df["sma200"])[ok]):
            total[d] += 1
            above[d] += int(a)
    return {d: above[d] / total[d] for d in total if total[d] >= 20}


def regime(b: float | None) -> str:
    if b is None:
        return "UNKNOWN"
    return "TREND_UP" if b >= BREADTH_TREND else ("TREND_DOWN" if b < BREADTH_DOWN else "CHOP")


def build(universe: dict, breadth: dict, asof: str) -> list:
    eps = []
    for t, df in universe.items():
        idx = list(df.index)
        o, h, l, c = (df[k].astype(float).tolist() for k in ("open", "high", "low", "close"))
        sig, atr, mom = df["sigma"].tolist(), df["atr"].tolist(), df["mom63"].tolist()
        for i in range(HISTORY, len(idx) - 20, STEP):
            if idx[i] > asof:
                break
            if not (sig[i] and sig[i] > 0 and atr[i] and atr[i] > 0 and c[i] > 0):
                continue
            j = min(len(idx), i + 1 + FORWARD)
            ep = R.Episode(oid="%s:%s" % (t, idx[i]), ticker=t, entry_date=idx[i],
                           entry=c[i], sigma=float(sig[i]), atr=float(atr[i]),
                           o=o[i + 1:j], h=h[i + 1:j], l=l[i + 1:j], c=c[i + 1:j],
                           dates=idx[i + 1:j], base_ret=0.0, base_days=0, base_open=False)
            ep.regime = regime(breadth.get(idx[i]))
            ep.momentum = bool(mom[i] is not None and not math.isnan(mom[i]) and mom[i] > 0)
            eps.append(ep)
    return eps


def _date_means(eps, res) -> dict:
    by = defaultdict(list)
    for e, r in zip(eps, res):
        by[e.entry_date].append(r.ret)
    return {d: sum(v) / len(v) for d, v in by.items()}


def evaluate(eps: list, cost_bps: float) -> dict:
    res = {name: [R.simulate(e, pol, cost_bps) for e in eps] for name, pol in POLICIES.items()}
    res["SPLIT"] = [R.Result(0.5 * a.ret + 0.5 * b.ret, round(0.5 * a.days + 0.5 * b.days), "SPLIT")
                    for a, b in zip(res["BOOK_ALL"], res["RUN_ALL"])]
    out = {}
    for scope in ("ALL", "TREND_UP", "CHOP", "TREND_DOWN"):
        for sub in ("ALL", "MOMENTUM"):
            keep = [k for k, e in enumerate(eps)
                    if (scope == "ALL" or e.regime == scope) and (sub == "ALL" or e.momentum)]
            if not keep:
                continue
            se = [eps[k] for k in keep]
            row = {}
            for name in ("BOOK_ALL", "RUN_ALL", "SPLIT"):
                m = R.measure(se, [res[name][k] for k in keep])
                row[name] = {"n": m.n, "dates": m.date_units, "date_mean": m.date_mean_ret,
                             "mean": m.mean_ret, "days": m.mean_days, "severe": m.severe_rate,
                             "worst": m.worst, "win_rate": m.win_rate}
            dm_b = _date_means(se, [res["BOOK_ALL"][k] for k in keep])
            dm_s = _date_means(se, [res["SPLIT"][k] for k in keep])
            dm_r = _date_means(se, [res["RUN_ALL"][k] for k in keep])
            row["split_beats_book_on_dates"] = round(
                100.0 * sum(1 for d in dm_b if dm_s[d] > dm_b[d]) / len(dm_b), 1)
            row["run_beats_book_on_dates"] = round(
                100.0 * sum(1 for d in dm_b if dm_r[d] > dm_b[d]) / len(dm_b), 1)
            out["%s/%s" % (scope, sub)] = row
    by_year = defaultdict(list)
    for k, e in enumerate(eps):
        by_year[e.entry_date[:4]].append(k)
    out["by_year"] = {}
    for y, keep in sorted(by_year.items()):
        se = [eps[k] for k in keep]
        out["by_year"][y] = {name: R.measure(se, [res[name][k] for k in keep]).date_mean_ret
                             for name in ("BOOK_ALL", "RUN_ALL", "SPLIT")}
    return out


def verdict(ev: dict) -> str:
    """The pre-registered rule, applied mechanically."""
    def holds(key):
        row = ev.get(key)
        if not row:
            return False
        s, b = row["SPLIT"], row["BOOK_ALL"]
        return (row["split_beats_book_on_dates"] > 50.0 and s["severe"] <= b["severe"]
                and s["worst"] >= b["worst"])
    if holds("TREND_UP/ALL") and holds("CHOP/ALL"):
        return "SPLIT PREFERRED"
    return "BOOK_ALL STANDS"


def run(root: Path, market: str, asof: str) -> dict:
    m = market.lower()
    uni = load_universe(root, m)
    br = breadth_by_date(uni)
    eps = build(uni, br, asof)
    ev = evaluate(eps, R.COST_BPS.get(m, 10.0))
    regimes = defaultdict(int)
    for e in eps:
        regimes[e.regime] += 1
    return {"market": m, "asof": asof, "tickers": len(uni), "episodes": len(eps),
            "entry_dates": len({e.entry_date for e in eps}),
            "first_entry": min(e.entry_date for e in eps) if eps else None,
            "regime_counts": dict(regimes), "policies": POLICIES,
            "results": ev, "verdict": verdict(ev),
            "decision_rule": "SPLIT only if it wins on >50% of entry dates in BOTH "
                             "TREND_UP and CHOP with severe and worst no worse"}

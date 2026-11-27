"""AEGIS · exit policy replay · research only, both markets.

CEO 2026-11-26.

QUESTION
--------
AEGIS exits only on a trailing stop. Winners are held 30-115 days while
profits leak back, and USA's stops walk down with the price. Would a
DYNAMIC exit - barriers scaled to each stock's own volatility, with a
horizon chosen from the evidence rather than fixed at 60/90 days - have
done better on the positions AEGIS actually held?

METHOD
------
Triple-barrier exits, volatility-scaled (Lopez de Prado, AFML ch.3):

    sigma   daily st.dev of log returns over the 20 bars UP TO entry
    TP      entry * exp( +k_tp * sigma * sqrt(h))
    SL      entry * exp( -k_sl * sigma * sqrt(h))
    TIME    exit at the close of bar h if neither barrier was touched

plus a variant with a give-back trail (exit when the close falls
k_trail * ATR below the post-entry high), and a pure chandelier trail.

Fills are conservative: a gap through a barrier fills at the OPEN, and a
bar touching BOTH barriers is scored as the stop. Every input is
point-in-time - sigma and ATR come only from bars on or before entry.

EVIDENCE DISCIPLINE (aegis_ml_discovery_guardrails)
--------------------------------------------------
Rows are not evidence: 479 of USA's 901 R2 episodes share one entry date.
So orphan auto-closes and phantom admissions are excluded, metrics are
reported per entry-DATE as well as per episode, the policy is chosen on
the earlier 60% of entry dates and judged only on the later 40%, and a
market with too few validation dates is reported INSUFFICIENT EVIDENCE
rather than given a winner.

This module decides nothing. It writes a report.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

EXCLUDE_REASONS = ("ORPHAN_AUTO_CLOSE", "ADMIN_PHANTOM")
COST_BPS = {"india": 20.0, "usa": 10.0}       # round trip, deducted per exit
MAX_BARS = 90
MIN_VALIDATION_DATES = 8
SEVERE = -8.0


@dataclass
class Episode:
    oid: str
    ticker: str
    entry_date: str
    entry: float
    sigma: float
    atr: float
    o: list
    h: list
    l: list
    c: list
    dates: list
    base_ret: float
    base_days: int
    base_open: bool


@dataclass
class Result:
    ret: float
    days: int
    reason: str


@dataclass
class Metrics:
    n: int = 0
    date_units: int = 0
    mean_ret: float = 0.0
    date_mean_ret: float = 0.0
    win_rate: float = 0.0
    mean_days: float = 0.0
    ret_per_day: float = 0.0
    severe_rate: float = 0.0
    worst: float = 0.0
    winners_cut: int = 0
    reasons: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# data
# ─────────────────────────────────────────────────────────────

def bars_path(root: Path, market: str, ticker: str) -> Path | None:
    base = (Path(root) / ("usa/data/raw/us" if market == "usa" else "data/raw/india"))
    t = str(ticker).upper().removesuffix(".NS").removesuffix(".BO")
    for cand in (t, t.replace(".", "-"), t.replace(".", "_"), t.replace(".", "")):
        p = base / f"{cand}_D1.parquet"
        if p.exists():
            return p
    return None


def load_bars(root: Path, market: str, ticker: str):
    p = bars_path(root, market, ticker)
    if p is None:
        return None
    df = pd.read_parquet(p)
    df.columns = [str(c).lower() for c in df.columns]
    if not {"open", "high", "low", "close"} <= set(df.columns):
        return None
    df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
    return df[~df.index.duplicated(keep="last")].sort_index()


def pit_sigma_atr(df, entry_date: str, n_sig: int = 20, n_atr: int = 14):
    """Volatility known AT entry - bars on or before the entry date only."""
    hist = df[df.index <= entry_date]
    if len(hist) < max(n_sig, n_atr) + 1:
        return None, None
    lr = (hist["close"] / hist["close"].shift(1)).apply(
        lambda x: math.log(x) if x and x > 0 else float("nan")).dropna()
    sigma = float(lr.iloc[-n_sig:].std())
    prev = hist["close"].shift(1)
    tr = pd.concat([hist["high"] - hist["low"], (hist["high"] - prev).abs(),
                    (hist["low"] - prev).abs()], axis=1).max(axis=1)
    atr = float(tr.iloc[-n_atr:].mean())
    if not (sigma > 0 and atr > 0):
        return None, None
    return sigma, atr


def _excluded(reason: str) -> bool:
    r = str(reason or "")
    return any(x in r for x in EXCLUDE_REASONS)


def build_episodes(root: Path, market: str, asof: str) -> list:
    from backend.research.opportunity_registry import load_all

    m = market.lower()
    out, cache = [], {}
    for opps in load_all(root).values():
        for o in opps:
            if o.market.lower() != m or o.runner != "R2" or not o.created_date:
                continue
            if o.status == "CLOSED" and _excluded(o.closed_reason):
                continue
            t = str(o.ticker).upper()
            if t not in cache:
                cache[t] = load_bars(root, m, t)
            df = cache[t]
            if df is None:
                continue
            ed = str(o.created_date)[:10]
            on = df[df.index <= ed]
            if on.empty:
                continue
            entry = float(on["close"].iloc[-1])
            sigma, atr = pit_sigma_atr(df, ed)
            if sigma is None or entry <= 0:
                continue
            fwd = df[(df.index > ed) & (df.index <= str(asof)[:10])].iloc[:MAX_BARS]
            if fwd.empty:
                continue
            if o.status == "CLOSED" and o.closed_date:
                upto = fwd[fwd.index <= str(o.closed_date)[:10]]
                if upto.empty:
                    continue
                base_px, base_days, base_open = float(upto["close"].iloc[-1]), len(upto), False
            else:
                base_px, base_days, base_open = float(fwd["close"].iloc[-1]), len(fwd), True
            out.append(Episode(
                oid=o.opportunity_id, ticker=t, entry_date=ed, entry=entry,
                sigma=sigma, atr=atr,
                o=fwd["open"].astype(float).tolist(), h=fwd["high"].astype(float).tolist(),
                l=fwd["low"].astype(float).tolist(), c=fwd["close"].astype(float).tolist(),
                dates=list(fwd.index),
                base_ret=(base_px / entry - 1) * 100, base_days=base_days,
                base_open=base_open))
    return out


# ─────────────────────────────────────────────────────────────
# policies
# ─────────────────────────────────────────────────────────────

def simulate_run(ep: Episode, pol: dict, cost_bps: float) -> Result:
    """LET WINNERS RUN, BUT NEVER WAIT ON A LOSER. CEO 2026-11-26.

    Before the target: the volatility stop. Once the target is touched or
    the stock is still rising (5-bar momentum up and above entry), it is
    NOT sold - it switches to a trail at peak - k_trail * ATR. At bar h a
    position that is not running is exited; a runner continues to the hard
    cap h_max.
    """
    h, h_max = int(pol["h"]), int(pol["h_max"])
    span = ep.sigma * math.sqrt(h)
    sl = ep.entry * math.exp(-pol["k_sl"] * span)
    tp = ep.entry * math.exp(pol["k_tp"] * span)
    k_tr = pol["k_trail"]
    cost = cost_bps / 100.0
    peak, running = ep.entry, False
    n = min(h_max, len(ep.c))
    for i in range(n):
        o, hi, lo, c = ep.o[i], ep.h[i], ep.l[i], ep.c[i]
        trail = peak - k_tr * ep.atr if running else None
        floor = max(sl, trail) if trail else sl
        if o <= floor:
            return Result((o / ep.entry - 1) * 100 - cost, i + 1,
                          "TRAIL_GAP" if running else "STOP_GAP")
        if lo <= floor:
            return Result((floor / ep.entry - 1) * 100 - cost, i + 1,
                          "TRAIL" if running else "STOP")
        peak = max(peak, hi)
        if hi >= tp:
            running = True
        rising = i >= 5 and c > ep.c[i - 5] and c > ep.entry
        if i + 1 == h and not (running or rising):
            return Result((c / ep.entry - 1) * 100 - cost, i + 1, "TIME")
        if i + 1 >= h and rising:
            running = True
    last = ep.c[n - 1]
    return Result((last / ep.entry - 1) * 100 - (cost if n == h_max else 0.0), n,
                  "MAX_HOLD" if n == h_max else "OPEN")


def efficiency_ratio(entry: float, closes: list) -> float:
    """Kaufman efficiency since entry: |net move| / total path travelled.

    1.0 is a straight line, ~0 is noise. Uses only the closes passed in,
    so at decision bar i it sees bars 0..i and nothing after.
    """
    path = abs(closes[0] - entry) + sum(abs(closes[k] - closes[k - 1])
                                        for k in range(1, len(closes)))
    return abs(closes[-1] - entry) / path if path > 0 else 0.0


def simulate_adapt(ep: Episode, pol: dict, cost_bps: float) -> Result:
    """DYNAMIC HOLD PERIOD · decided per position by its own trend quality.

    CEO 2026-11-26: "profit rising can be held longer, but we need a
    calculation and should not wait so long".

    Letting every position run beat a fixed 10-day exit on average only
    through a few large winners (ADT +5 -> +58%) and lost on 16 of 19
    entry dates. So the extension is earned, not granted: at the target,
    or at bar h, a position keeps running only if its efficiency ratio
    since entry is >= er_min AND it is in profit. Otherwise it is booked
    (at the target) or exited (at h). A runner trails at peak - k * ATR
    and is capped at h_max.
    """
    h, h_max, er_min = int(pol["h"]), int(pol["h_max"]), float(pol["er_min"])
    span = ep.sigma * math.sqrt(h)
    sl = ep.entry * math.exp(-pol["k_sl"] * span)
    tp = ep.entry * math.exp(pol["k_tp"] * span)
    k_tr = pol["k_trail"]
    cost = cost_bps / 100.0
    peak, running = ep.entry, False
    n = min(h_max, len(ep.c))
    for i in range(n):
        o, hi, lo, c = ep.o[i], ep.h[i], ep.l[i], ep.c[i]
        floor = max(sl, peak - k_tr * ep.atr) if running else sl
        if o <= floor:
            return Result((o / ep.entry - 1) * 100 - cost, i + 1,
                          "TRAIL_GAP" if running else "STOP_GAP")
        if lo <= floor:
            return Result((floor / ep.entry - 1) * 100 - cost, i + 1,
                          "TRAIL" if running else "STOP")
        peak = max(peak, hi)
        er = efficiency_ratio(ep.entry, ep.c[:i + 1])
        if not running and hi >= tp:
            if er >= er_min:
                running = True
            else:
                return Result((tp / ep.entry - 1) * 100 - cost, i + 1, "TAKE_PROFIT")
        if not running and i + 1 == h:
            if er >= er_min and c > ep.entry:
                running = True
            else:
                return Result((c / ep.entry - 1) * 100 - cost, i + 1, "TIME")
    last = ep.c[n - 1]
    return Result((last / ep.entry - 1) * 100 - (cost if n == h_max else 0.0), n,
                  "MAX_HOLD" if n == h_max else "OPEN")


def simulate(ep: Episode, pol: dict, cost_bps: float) -> Result:
    if pol["kind"] == "TB_ADAPT":
        return simulate_adapt(ep, pol, cost_bps)
    if pol["kind"] == "TB_RUN":
        return simulate_run(ep, pol, cost_bps)
    kind, hh = pol["kind"], int(pol["h"])
    span = ep.sigma * math.sqrt(hh)
    tp = ep.entry * math.exp(pol["k_tp"] * span) if pol.get("k_tp") else None
    sl = ep.entry * math.exp(-pol["k_sl"] * span)
    k_tr = pol.get("k_trail")
    peak = ep.entry
    n = min(hh, len(ep.c))
    cost = cost_bps / 100.0
    for i in range(n):
        o, hi, lo, c = ep.o[i], ep.h[i], ep.l[i], ep.c[i]
        if o <= sl:
            return Result((o / ep.entry - 1) * 100 - cost, i + 1, "STOP_GAP")
        if tp and o >= tp:
            return Result((o / ep.entry - 1) * 100 - cost, i + 1, "TAKE_PROFIT_GAP")
        if lo <= sl:
            return Result((sl / ep.entry - 1) * 100 - cost, i + 1, "STOP")
        if tp and hi >= tp:
            return Result((tp / ep.entry - 1) * 100 - cost, i + 1, "TAKE_PROFIT")
        peak = max(peak, hi)
        if k_tr and peak > ep.entry * (1 + span) and c < peak - k_tr * ep.atr:
            return Result((c / ep.entry - 1) * 100 - cost, i + 1, "TRAIL")
    last = ep.c[n - 1]
    return Result((last / ep.entry - 1) * 100 - (cost if n == hh else 0.0), n,
                  "TIME" if n == hh else "OPEN")


def policy_grid() -> list:
    grid = []
    for h in (5, 10, 15, 20, 30, 45, 60):
        for k_sl in (1.0, 1.5, 2.0):
            for k_tp in (1.0, 1.5, 2.0, 3.0):
                grid.append({"kind": "TB", "h": h, "k_tp": k_tp, "k_sl": k_sl})
                for k_tr in (2.0, 3.0):
                    grid.append({"kind": "TB_TRAIL", "h": h, "k_tp": k_tp,
                                 "k_sl": k_sl, "k_trail": k_tr})
            for k_tr in (2.0, 3.0, 4.0):
                grid.append({"kind": "CHANDELIER", "h": h, "k_tp": None,
                             "k_sl": k_sl, "k_trail": k_tr})
    for h in (5, 10, 15, 20):
        for k_sl in (1.0, 1.5):
            for k_tp in (1.0, 1.5, 2.0):
                for k_tr in (2.0, 3.0):
                    for h_max in (30, 45, 60):
                        grid.append({"kind": "TB_RUN", "h": h, "k_tp": k_tp,
                                     "k_sl": k_sl, "k_trail": k_tr, "h_max": h_max})
    for h in (5, 10):
        for er_min in (0.2, 0.3, 0.4, 0.5, 0.6):
            for k_tr in (2.0, 3.0):
                for h_max in (20, 30, 45):
                    grid.append({"kind": "TB_ADAPT", "h": h, "k_tp": 1.0, "k_sl": 1.0,
                                 "k_trail": k_tr, "h_max": h_max, "er_min": er_min})
    return grid


def label(pol: dict) -> str:
    if pol["kind"] == "BASELINE":
        return "BASELINE (what AEGIS did)"
    parts = ["%s h=%dd" % (pol["kind"], pol["h"]), "sl=%.1f" % pol["k_sl"]]
    if pol.get("k_tp"):
        parts.append("tp=%.1f" % pol["k_tp"])
    if pol.get("k_trail"):
        parts.append("trail=%.1fATR" % pol["k_trail"])
    if pol.get("h_max"):
        parts.append("max=%dd" % pol["h_max"])
    if pol.get("er_min") is not None:
        parts.append("ER>=%.1f" % pol["er_min"])
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────
# metrics
# ─────────────────────────────────────────────────────────────

def measure(eps: list, results: list) -> Metrics:
    mt = Metrics()
    if not eps:
        return mt
    rets = [r.ret for r in results]
    days = [r.days for r in results]
    by_date = defaultdict(list)
    for e, r in zip(eps, results):
        by_date[e.entry_date].append(r.ret)
    reasons = defaultdict(int)
    for r in results:
        reasons[r.reason] += 1
    mt.n = len(eps)
    mt.date_units = len(by_date)
    mt.mean_ret = round(sum(rets) / len(rets), 3)
    mt.date_mean_ret = round(sum(sum(v) / len(v) for v in by_date.values()) / len(by_date), 3)
    mt.win_rate = round(100.0 * sum(1 for x in rets if x > 0) / len(rets), 1)
    mt.mean_days = round(sum(days) / len(days), 1)
    mt.ret_per_day = round(sum(rets) / max(sum(days), 1), 4)
    mt.severe_rate = round(100.0 * sum(1 for x in rets if x <= SEVERE) / len(rets), 1)
    mt.worst = round(min(rets), 2)
    mt.winners_cut = sum(1 for e, r in zip(eps, results)
                         if e.base_ret >= 5.0 and r.ret < e.base_ret - 5.0)
    mt.reasons = dict(reasons)
    return mt


def baseline_results(eps: list) -> list:
    return [Result(e.base_ret, e.base_days, "OPEN" if e.base_open else "CLOSED")
            for e in eps]


def run(root: Path, market: str, asof: str) -> dict:
    m = market.lower()
    cost = COST_BPS.get(m, 10.0)
    eps = build_episodes(root, m, asof)
    dates = sorted({e.entry_date for e in eps})
    cut = dates[int(len(dates) * 0.6)] if len(dates) >= 2 else (dates[0] if dates else "")
    cal = [e for e in eps if e.entry_date < cut]
    val = [e for e in eps if e.entry_date >= cut]

    base_cal = measure(cal, baseline_results(cal))
    base_val = measure(val, baseline_results(val))

    scored = []
    for pol in policy_grid():
        mc = measure(cal, [simulate(e, pol, cost) for e in cal])
        scored.append((pol, mc))

    # Choose on calibration only: best capital efficiency, never worse on
    # severe losses than what AEGIS did, and positive on average.
    ok = [(p, mc) for p, mc in scored
          if mc.n and mc.mean_ret > 0 and mc.severe_rate <= base_cal.severe_rate]
    pick = max(ok, key=lambda t: t[1].ret_per_day) if ok else None

    by_h = {}
    for h in (5, 10, 15, 20, 30, 45, 60):
        cand = [(p, mc) for p, mc in ok if p["h"] == h]
        if cand:
            p, mc = max(cand, key=lambda t: t[1].ret_per_day)
            mv = measure(val, [simulate(e, p, cost) for e in val])
            by_h[h] = {"policy": p, "label": label(p),
                       "calibration": vars(mc), "validation": vars(mv)}

    verdict, chosen = "INSUFFICIENT EVIDENCE", None
    if pick:
        p, mc = pick
        mv = measure(val, [simulate(e, p, cost) for e in val])
        chosen = {"policy": p, "label": label(p),
                  "calibration": vars(mc), "validation": vars(mv)}
        vdates = len({e.entry_date for e in val})
        if vdates < MIN_VALIDATION_DATES:
            verdict = "INSUFFICIENT EVIDENCE"
        elif (mv.ret_per_day > base_val.ret_per_day
              and mv.severe_rate <= base_val.severe_rate
              and mv.date_mean_ret >= base_val.date_mean_ret):
            verdict = "SUPPORTED"
        else:
            verdict = "NOT SUPPORTED"

    return {
        "market": m, "asof": asof, "cost_bps_round_trip": cost,
        "population": {"episodes": len(eps), "entry_dates": len(dates),
                       "calibration_episodes": len(cal), "validation_episodes": len(val),
                       "calibration_dates": len({e.entry_date for e in cal}),
                       "validation_dates": len({e.entry_date for e in val}),
                       "split_date": cut,
                       "excluded_reasons": list(EXCLUDE_REASONS)},
        "baseline": {"calibration": vars(base_cal), "validation": vars(base_val)},
        "chosen": chosen,
        "best_by_horizon": by_h,
        "n_policies_tested": len(scored),
        "verdict": verdict,
    }


# ─────────────────────────────────────────────────────────────
# nested cross-validation by entry-date block
# ─────────────────────────────────────────────────────────────
#
# One 60/40 split was not enough: USA's later 40% of dates were on
# average 5 days old, so every horizon above 5 days scored identically to
# the baseline and the comparison measured censoring, not the policy.
#
# Here only MATURE episodes count (closed, or >= MIN_MATURE_BARS of
# forward bars), the entry dates are cut into K contiguous blocks, and
# for each block the policy is CHOSEN on the other blocks and SCORED on
# the held-out one. The pooled held-out result estimates what this way of
# choosing a policy would actually deliver on dates it never saw - the
# number that survives testing 315 configurations.

MIN_MATURE_BARS = 20
K_FOLDS = 5


def _mature(e: Episode) -> bool:
    return (not e.base_open) or len(e.c) >= MIN_MATURE_BARS


def _choose(eps: list, cost: float, base_severe: float, kinds=None):
    best = None
    for pol in policy_grid():
        if kinds and pol["kind"] not in kinds:
            continue
        mt = measure(eps, [simulate(e, pol, cost) for e in eps])
        if mt.n and mt.mean_ret > 0 and mt.severe_rate <= base_severe:
            if best is None or mt.ret_per_day > best[1].ret_per_day:
                best = (pol, mt)
    return best


def run_cv(root: Path, market: str, asof: str, eps: list | None = None,
           kinds=None) -> dict:
    m = market.lower()
    cost = COST_BPS.get(m, 10.0)
    eps = [e for e in (eps if eps is not None else build_episodes(root, m, asof))
           if _mature(e)]
    dates = sorted({e.entry_date for e in eps})
    if len(dates) < K_FOLDS * 2:
        return {"verdict": "INSUFFICIENT EVIDENCE", "mature_episodes": len(eps),
                "mature_dates": len(dates), "folds": []}
    size = math.ceil(len(dates) / K_FOLDS)
    blocks = [dates[i:i + size] for i in range(0, len(dates), size)]
    folds, oof_eps, oof_res = [], [], []
    for b in blocks:
        bs = set(b)
        test = [e for e in eps if e.entry_date in bs]
        train = [e for e in eps if e.entry_date not in bs]
        if not test or not train:
            continue
        base_tr = measure(train, baseline_results(train))
        pick = _choose(train, cost, base_tr.severe_rate, kinds=kinds)
        base_te = measure(test, baseline_results(test))
        if pick is None:
            res = baseline_results(test)            # no policy qualified: keep AEGIS
            chosen = "BASELINE (no policy qualified on train)"
        else:
            res = [simulate(e, pick[0], cost) for e in test]
            chosen = label(pick[0])
        mt = measure(test, res)
        fallback = pick is None
        folds.append({"dates": "%s..%s" % (b[0], b[-1]), "n_test": len(test),
                      "fallback_to_baseline": fallback,
                      "chosen_on_train": chosen,
                      "test": vars(mt), "baseline_test": vars(base_te),
                      "improved": (mt.date_mean_ret > base_te.date_mean_ret
                                   and mt.severe_rate <= base_te.severe_rate)})
        # A block where nothing qualified falls back to AEGIS's own result.
        # That block says nothing about the policy family, so it is kept
        # out of the pooled score - measured 2026-11-26, one such block
        # (+10.01% per date, -53.7% worst) made two families look better
        # than they were.
        if not fallback:
            oof_eps += test
            oof_res += res
    oof = measure(oof_eps, oof_res)
    base = measure(oof_eps, baseline_results(oof_eps))
    n_imp = sum(1 for f in folds if f["improved"] and not f["fallback_to_baseline"])
    if (oof.date_mean_ret > base.date_mean_ret and oof.severe_rate <= base.severe_rate
            and n_imp >= math.ceil(len(folds) * 0.6)):
        verdict = "SUPPORTED"
    elif oof.severe_rate < base.severe_rate and oof.date_mean_ret >= base.date_mean_ret - 0.5:
        verdict = "RISK REDUCTION ONLY"
    else:
        verdict = "NOT SUPPORTED"
    return {"verdict": verdict, "mature_episodes": len(eps), "mature_dates": len(dates),
            "folds_improved": n_imp,
            "n_folds": sum(1 for f in folds if not f["fallback_to_baseline"]),
            "n_fallback_folds": sum(1 for f in folds if f["fallback_to_baseline"]),
            "out_of_fold": vars(oof), "baseline": vars(base), "folds": folds}

"""WAVE 2C · SEVEN-FILTER AI RESEARCH · CEO 2026-09-08.

> "The mistake would be turning this into `7 filters = BUY`. Instead, AI
>  should investigate which combinations, trends, exceptions and
>  transitions within these seven filters historically produce the best
>  outcomes."

THE HUMAN BASELINE IS THE THING TO BEAT
----------------------------------------
The seven filters are the interpretable baseline:

    1 sales growth  > 10%      2 profit growth > 10%
    3 ROE           > 15%      4 D/E           < 0.5
    5 positive cash flow       6 reasonable P/E
    7 no governance concerns

Filters 6 and 7 are NOT computed here: no PIT share count exists for a
P/E, and no governance dataset exists at all. Claiming five filters is
honest; claiming seven would not be. `n_filters_available` is reported on
every row so nothing silently pretends otherwise.

AI has to beat that baseline on the same rows. If passing 4 of 5 filters
separates outcomes as well as any learned state, the filters win and the
model is killed.

WHAT IS TESTED · the directive's ten dimensions
-----------------------------------------------
  1 LEVEL          does the filter pass today
  2 TREND          is the metric improving across quarters
  3 ACCELERATION   is the improvement itself speeding up
  4 RELATIVE       rank within the cohort on that date
  5 SURPRISE       earnings surprise, PIT-dated
  6 QUALITY        CFO/NI, FCF/NI, accrual proxy
  7 INTERACTIONS   growth x ROE-trend x leverage
  8 FAILURE STATES which combinations precede severe loss
  9 AI STATES      left to Wave 2E clustering · deliberately not forced here
 10 INCREMENTAL    the only test that decides anything

THE EXCEPTION THE DIRECTIVE ASKED ABOUT
----------------------------------------
> "ROE 12 -> 16 -> 21 versus ROE 24 -> 20 -> 16. The first might be much
>  more attractive despite starting below 15%."

A level-only filter FAILS the first and PASSES the second. This module
reports both populations separately - `rising_but_failing` and
`passing_but_falling` - so that claim is measured rather than assumed.

PIT LAG SENSITIVITY IS BUILT IN, NOT BOLTED ON
-----------------------------------------------
Every result is computed at 30, 45 and 60 assumed publication days. A
finding that changes with the lag is an artefact of my assumption, and is
reported as such.

RESEARCH ONLY · no engine, no threshold, no promotion.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.seven_filter_ai.v1"
FAMILY = "R3E_SEVEN_FILTER_V1"

HORIZON = "fwd_10d_pct"
LAGS = [30, 45, 60]
SEVERE_Q = 0.10

FILTERS = ["sales_growth_gt10", "profit_growth_gt10", "roe_gt15",
           "de_lt05", "positive_cashflow"]
NOT_COMPUTABLE = {"reasonable_pe": "no PIT share count · no P/E possible",
                  "no_governance_concerns": "no governance dataset exists"}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _growth(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return (cur / abs(prev) - 1.0) * 100


def filter_state(periods: list) -> dict:
    """Level + trend + acceleration for each computable filter."""
    out = {"n_periods": len(periods)}
    if len(periods) < 2:
        return out
    last, prev = periods[-1], periods[-2]

    def series(key):
        return [p.get(key) for p in periods]

    def latest(key):
        """Most recent NON-NULL value and how many periods back it came from.

        Balance-sheet and cash-flow lines are reported sparsely by the
        provider: ADANIGREEN's newest period carries revenue and net income
        but no equity, so reading only periods[-1] returned None for ROE
        and D/E and discarded 555 of 619 rows. Carrying the last known
        value forward is standard for mixed-frequency fundamentals and is
        PIT-safe in the conservative direction - an older figure was
        certainly available. Staleness is recorded, never hidden.
        """
        for back, v in enumerate(reversed(series(key))):
            if v is not None:
                return v, back
        return None, None

    rev = series("revenue")
    ni = series("net_income")
    eq = series("total_equity")
    debt = series("total_debt")
    ocf = series("operating_cashflow")
    eq_v, eq_back = latest("total_equity")
    debt_v, debt_back = latest("total_debt")
    ocf_v, ocf_back = latest("operating_cashflow")
    ni_v, ni_back = latest("net_income")
    out["staleness_periods"] = {"equity": eq_back, "debt": debt_back,
                                "ocf": ocf_back, "net_income": ni_back}

    # ── 1 LEVEL ────────────────────────────────────────────────────────
    g_rev = _growth(rev[-1], rev[-5]) if len(rev) >= 5 else _growth(rev[-1], rev[-2])
    g_ni = _growth(ni[-1], ni[-5]) if len(ni) >= 5 else _growth(ni[-1], ni[-2])
    roe = (ni_v / eq_v * 100) if (ni_v is not None and eq_v) else None
    de = (debt_v / eq_v) if (debt_v is not None and eq_v) else None
    out["sales_growth_pct"] = None if g_rev is None else round(g_rev, 3)
    out["profit_growth_pct"] = None if g_ni is None else round(g_ni, 3)
    out["roe_pct"] = None if roe is None else round(roe, 3)
    out["debt_to_equity"] = None if de is None else round(de, 4)
    out["operating_cashflow"] = ocf_v

    out["sales_growth_gt10"] = None if g_rev is None else int(g_rev > 10)
    out["profit_growth_gt10"] = None if g_ni is None else int(g_ni > 10)
    out["roe_gt15"] = None if roe is None else int(roe > 15)
    out["de_lt05"] = None if de is None else int(de < 0.5)
    out["positive_cashflow"] = None if ocf_v is None else int(ocf_v > 0)

    got = [out[f] for f in FILTERS if out.get(f) is not None]
    out["n_filters_available"] = len(got)
    out["n_filters_passed"] = sum(got) if got else None
    out["filters_pass_rate"] = (round(sum(got) / len(got), 4) if got else None)

    # ── 2 TREND · 3 ACCELERATION ───────────────────────────────────────
    def roe_at(i):
        return (ni[i] / eq[i] * 100) if (ni[i] is not None and eq[i]) else None
    roes = [roe_at(i) for i in range(len(ni))]
    roes = [r for r in roes if r is not None]
    out["roe_trend_pp"] = (round(roes[-1] - roes[-2], 3)
                           if len(roes) >= 2 else None)
    out["roe_accel_pp"] = (round((roes[-1] - roes[-2]) - (roes[-2] - roes[-3]), 3)
                           if len(roes) >= 3 else None)
    g1 = _growth(rev[-1], rev[-2])
    g2 = _growth(rev[-2], rev[-3]) if len(rev) >= 3 else None
    out["sales_growth_accel_pp"] = (round(g1 - g2, 3)
                                    if (g1 is not None and g2 is not None)
                                    else None)
    des = [(debt[i] / eq[i]) if (debt[i] is not None and eq[i]) else None
           for i in range(len(debt))]
    des = [d for d in des if d is not None]
    out["de_trend"] = round(des[-1] - des[-2], 4) if len(des) >= 2 else None

    # ── THE EXCEPTION THE DIRECTIVE ASKED ABOUT ────────────────────────
    # ROE 12->16->21 fails a level filter; ROE 24->20->16 passes it.
    out["roe_rising_but_failing"] = int(
        out.get("roe_gt15") == 0 and (out.get("roe_trend_pp") or 0) > 0)
    out["roe_passing_but_falling"] = int(
        out.get("roe_gt15") == 1 and (out.get("roe_trend_pp") or 0) < 0)

    # ── 6 QUALITY · is profit becoming cash ────────────────────────────
    out["cfo_to_net_income"] = (round(ocf_v / ni_v, 4)
                                if (ocf_v is not None and ni_v) else None)
    out["accrual_proxy"] = (round((ni_v - ocf_v) / abs(ni_v), 4)
                            if (ni_v and ocf_v is not None) else None)
    return out


def build(root: Path, market: str, lag_days: int) -> list:
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    from backend.research.substrate import fundamental_timeseries as ft

    store = ft.load(root, market)
    if not store:
        return []
    recs = store.get("tickers") or {}
    rows = load_cohort(root, market)
    seen, out = set(), []
    for r in rows:
        t = str(r.get("ticker") or "").upper().split(".", 1)[0]
        d = str(r.get("prediction_date") or "")[:10]
        fwd = _num(r.get(HORIZON))
        if not t or not d or fwd is None or (t, d) in seen or t not in recs:
            continue
        seen.add((t, d))
        ps = ft.as_of(recs[t], d, lag_days)
        st = filter_state(ps)
        if st.get("n_filters_available", 0) < 3:
            continue
        e = {"ticker": t, "date": d, "fwd": fwd,
             "vol_20d_pct": _num(r.get("vol_20d_pct")),
             "momentum_20d_pct": _num(r.get("momentum_20d_pct")),
             "ma200_dist_pct": _num(r.get("ma200_dist_pct")),
             "confidence_pct": _num(r.get("confidence_pct"))}
        e.update(st)
        f = ft.features_as_of(recs[t], d, lag_days)
        e["h3_last_surprise_pct"] = f.get("h3_last_surprise_pct")
        e["h3_surprise_mean_4q"] = f.get("h3_surprise_mean_4q")
        e["pit_status"] = f.get("pit_status")
        out.append(e)
    # ── 4 RELATIVE · rank within the same date ─────────────────────────
    by_date = {}
    for e in out:
        by_date.setdefault(e["date"], []).append(e)
    for d, g in by_date.items():
        for key in ("sales_growth_pct", "roe_pct"):
            vals = sorted((x[key] for x in g if x.get(key) is not None))
            for x in g:
                v = x.get(key)
                x[f"rel_{key}_pctile"] = (
                    round(sum(1 for u in vals if u <= v) / len(vals), 4)
                    if (v is not None and vals) else None)
    return out


def _mw_p(a: list, b: list) -> Optional[float]:
    """Two-sided Mann-Whitney U, normal approximation with tie correction."""
    if len(a) < 8 or len(b) < 8:
        return None
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i, n = [0.0] * len(allv), 0, len(allv)
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and allv[j + 1][0] == allv[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[k] = avg
        t = j - i + 1
        tie_term += t ** 3 - t
        i = j + 1
    ra = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    na, nb = len(a), len(b)
    u = ra - na * (na + 1) / 2.0
    mu = na * nb / 2.0
    var = na * nb * (n + 1) / 12.0 - na * nb * tie_term / (12.0 * n * (n - 1))
    if var <= 0:
        return None
    z = (u - mu) / math.sqrt(var)
    return round(math.erfc(abs(z) / math.sqrt(2)), 6)


def _within_ticker_delta(rows: list, pred) -> Optional[dict]:
    """Each ticker is its own control.

    A pooled with/without split in a 35-ticker cohort can be produced
    entirely by which NAMES fall on each side. This pairs the comparison
    inside each ticker, so the mix cannot generate the effect. If the
    pooled delta survives here it is about the fundamental state; if it
    collapses it was about the names.
    """
    by = {}
    for r in rows:
        by.setdefault(r["ticker"], ([], []))[0 if pred(r) else 1].append(r["fwd"])
    deltas = [sum(w) / len(w) - sum(o) / len(o)
              for w, o in by.values() if len(w) >= 3 and len(o) >= 3]
    if len(deltas) < 5:
        return {"n_tickers_paired": len(deltas),
                "verdict": "UNPAIRABLE · fewer than 5 names carry both states"}
    deltas.sort()
    pos = sum(1 for d in deltas if d > 0)
    return {"n_tickers_paired": len(deltas),
            "mean_within_delta_pp": round(sum(deltas) / len(deltas), 3),
            "median_within_delta_pp": round(deltas[len(deltas) // 2], 3),
            "share_positive_pct": round(pos / len(deltas) * 100, 1)}


def _ticker_constant(rows: list, pred) -> bool:
    """Does the predicate ever change WITHIN a ticker across the cohort?

    Fundamentals are quarterly. Across a one-month cohort a name's
    fundamental state does not move, so `roe_rising` is not a time-varying
    signal - it is a LABEL attached to a set of names. When that is true,
    a row-level test silently claims 333 independent observations when it
    holds ~35, and any p-value it produces is fiction.
    """
    for t in {r["ticker"] for r in rows}:
        g = {pred(r) for r in rows if r["ticker"] == t}
        if len(g) > 1:
            return False
    return True


def _ticker_level_test(rows: list, pred) -> dict:
    """The honest unit of analysis when a predicate is ticker-constant.

    One observation per NAME - its mean forward return - so the test
    counts the units that actually vary.
    """
    means = {}
    for r in rows:
        means.setdefault(r["ticker"], []).append(r["fwd"])
    side = {t: pred(next(r for r in rows if r["ticker"] == t)) for t in means}
    a = [sum(v) / len(v) for t, v in means.items() if side[t]]
    b = [sum(v) / len(v) for t, v in means.items() if not side[t]]
    if len(a) < 3 or len(b) < 3:
        return {"n_tickers_with": len(a), "n_tickers_without": len(b),
                "verdict": "TOO FEW NAMES"}
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    return {"n_tickers_with": len(a), "n_tickers_without": len(b),
            "mean_of_ticker_means_with_pct": round(ma, 3),
            "mean_of_ticker_means_without_pct": round(mb, 3),
            "delta_pp": round(ma - mb, 3),
            "mannwhitney_p_ticker_level": _mw_p(a, b)}


def _stats(rows: list, sev_cut: float) -> dict:
    if not rows:
        return {"n": 0}
    f = [r["fwd"] for r in rows]
    return {"n": len(rows), "n_tickers": len({r["ticker"] for r in rows}),
            "mean_fwd_pct": round(sum(f) / len(f), 3),
            "median_fwd_pct": round(sorted(f)[len(f) // 2], 3),
            "win_rate_pct": round(sum(1 for v in f if v > 0) / len(f) * 100, 1),
            "severe_loss_rate_pct": round(
                sum(1 for v in f if v <= sev_cut) / len(f) * 100, 1)}


R2_FEATURES = ["confidence_pct", "vol_20d_pct", "momentum_20d_pct",
               "ma200_dist_pct"]
FUND_FEATURES = ["n_filters_passed", "roe_pct", "roe_trend_pp", "roe_accel_pp",
                 "sales_growth_pct", "sales_growth_accel_pp", "debt_to_equity",
                 "cfo_to_net_income", "h3_last_surprise_pct",
                 "rel_roe_pct_pctile", "rel_sales_growth_pct_pctile"]

MIN_EVENTS_FOR_INCREMENTAL = 40
MIN_EVENT_TICKERS = 15


def _auc(y, p) -> Optional[float]:
    pos = [i for i, v in enumerate(y) if v == 1]
    neg = [i for i, v in enumerate(y) if v == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(p)), key=lambda i: p[i])
    rank = [0.0] * len(p)
    for r, i in enumerate(order, 1):
        rank[i] = r
    a = ((sum(rank[i] for i in pos) - len(pos) * (len(pos) + 1) / 2)
         / (len(pos) * len(neg)))
    return round(a, 4)


def incremental_over_r2(rows: list, sev: float) -> dict:
    """DIMENSION 10 · the only test that decides anything.

    > "Incremental value over R2 - the non-negotiable final test."

    R2 already sees price, volatility, momentum and its own confidence. The
    question is not whether fundamentals predict severe loss; it is whether
    they predict anything R2 does not ALREADY know. Two models are fit on
    identical rows and identical folds, differing only by the fundamental
    block, and scored out-of-fold on TICKER-DISJOINT splits so a name
    cannot appear in both its own training and test data.

    If the delta is not clearly positive, the fundamental layer adds
    nothing and the MODEL is killed - not the finding, the model. That is
    the third standing kill switch.
    """
    y = [1 if r["fwd"] <= sev else 0 for r in rows]
    n_ev = sum(y)
    ev_tk = len({r["ticker"] for r, v in zip(rows, y) if v == 1})
    gate = {"n_rows": len(rows), "n_events": n_ev, "n_event_tickers": ev_tk,
            "min_events_required": MIN_EVENTS_FOR_INCREMENTAL,
            "min_event_tickers_required": MIN_EVENT_TICKERS}
    if n_ev < MIN_EVENTS_FOR_INCREMENTAL or ev_tk < MIN_EVENT_TICKERS:
        gate["verdict"] = (
            "REFUSED · %d severe-loss events across %d names cannot support an "
            "incremental-value test. Fitting it anyway would produce a number, "
            "not evidence. This is the correct outcome for a %d-row cohort and "
            "resolves as the substrate accrues." % (n_ev, ev_tk, len(rows)))
        return gate

    import numpy as np
    import lightgbm as lgb

    tickers = sorted({r["ticker"] for r in rows})
    fold_of = {t: i % 5 for i, t in enumerate(tickers)}

    def matrix(feats):
        return np.array([[(r.get(f) if r.get(f) is not None else float("nan"))
                          for f in feats] for r in rows], dtype=float)

    def oof(feats):
        X, pred = matrix(feats), [0.0] * len(rows)
        for k in range(5):
            te = [i for i, r in enumerate(rows) if fold_of[r["ticker"]] == k]
            tr = [i for i, r in enumerate(rows) if fold_of[r["ticker"]] != k]
            if not te or len({y[i] for i in tr}) < 2:
                return None
            m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                                   learning_rate=0.05, n_estimators=200,
                                   min_child_samples=20, reg_lambda=1.0,
                                   verbose=-1, random_state=20260908)
            m.fit(X[tr], np.array([y[i] for i in tr]))
            for i, pr in zip(te, m.predict_proba(X[te])[:, 1]):
                pred[i] = float(pr)
        return pred

    p_base = oof(R2_FEATURES)
    p_full = oof(R2_FEATURES + FUND_FEATURES)
    a_base = _auc(y, p_base) if p_base else None
    a_full = _auc(y, p_full) if p_full else None
    gate.update({"folds": "5 · ticker-disjoint",
                 "auc_r2_features_only": a_base,
                 "auc_r2_plus_fundamentals": a_full,
                 "delta_auc": (round(a_full - a_base, 4)
                               if (a_base is not None and a_full is not None)
                               else None)})

    # A point delta on 45 events means nothing without a CI. Resampling is
    # done over TICKERS, not rows, because rows of one name are not
    # independent draws - the same reason the dimension tests had to move to
    # ticker units.
    if a_base is not None and a_full is not None:
        rng = np.random.default_rng(20260908)
        idx_by_t = {}
        for i, r in enumerate(rows):
            idx_by_t.setdefault(r["ticker"], []).append(i)
        names, deltas = list(idx_by_t), []
        for _ in range(400):
            pick = rng.choice(len(names), size=len(names), replace=True)
            sel = [i for k in pick for i in idx_by_t[names[k]]]
            yb = [y[i] for i in sel]
            if len(set(yb)) < 2:
                continue
            ab = _auc(yb, [p_base[i] for i in sel])
            af = _auc(yb, [p_full[i] for i in sel])
            if ab is not None and af is not None:
                deltas.append(af - ab)
        if len(deltas) >= 100:
            deltas.sort()
            lo = deltas[int(0.025 * len(deltas))]
            hi = deltas[int(0.975 * len(deltas))]
            gate["delta_auc_ci95_ticker_bootstrap"] = [round(lo, 4), round(hi, 4)]
            gate["ci_excludes_zero"] = bool(lo > 0 or hi < 0)
            gate["n_bootstrap"] = len(deltas)

    d = gate.get("delta_auc")
    ci_ok = gate.get("ci_excludes_zero")
    if d is None:
        gate["verdict"] = "UNCOMPUTABLE · a fold carried a single class"
    elif ci_ok is False:
        gate["verdict"] = (
            "KILL MODEL · delta AUC %+.4f but the ticker-bootstrap 95%% CI "
            "%s spans zero. The point estimate is noise from %d events across "
            "%d names · no incremental value is demonstrated."
            % (d, gate.get("delta_auc_ci95_ticker_bootstrap"), n_ev, ev_tk))
    elif d <= 0.01:
        gate["verdict"] = (
            "KILL MODEL · fundamentals add %+.4f AUC over what R2 already "
            "sees. No incremental value · the third kill switch fires." % d)
    else:
        gate["verdict"] = (
            "INCREMENTAL SIGNAL %+.4f AUC · candidate only · needs "
            "out-of-sample confirmation before it means anything." % d)
    return gate


def analyse_lag(root: Path, market: str, lag: int) -> dict:
    rows = build(root, market, lag)
    if len(rows) < 60:
        return {"lag_days": lag, "skipped": "n=%d" % len(rows)}
    fwd = sorted(r["fwd"] for r in rows)
    sev = fwd[max(0, int(len(fwd) * SEVERE_Q) - 1)]
    out = {"lag_days": lag, "n": len(rows),
           "n_tickers": len({r["ticker"] for r in rows}),
           "severe_cut_pct": round(sev, 3),
           "population": _stats(rows, sev)}

    # ── HUMAN BASELINE · n filters passed ──────────────────────────────
    by_n = {}
    for r in rows:
        k = r.get("n_filters_passed")
        if k is not None:
            by_n.setdefault(int(k), []).append(r)
    out["baseline_by_filters_passed"] = {
        str(k): _stats(v, sev) for k, v in sorted(by_n.items())}
    out["baseline_caveat"] = (
        "The seven filters are a MULTI-YEAR ownership thesis. This cohort "
        "measures %s. A filter set can be entirely correct about five-year "
        "compounding and carry no signal - or an inverted one - over ten "
        "trading days, because short-horizon returns are dominated by "
        "momentum and flow. Any monotonicity seen here is a statement about "
        "this horizon only, and must NOT be read as a verdict on the "
        "filters themselves." % HORIZON)

    # ── TREND / ACCELERATION vs LEVEL ──────────────────────────────────
    def split(pred, label):
        a = [r for r in rows if pred(r)]
        b = [r for r in rows if not pred(r)]
        if len(a) < 20 or len(b) < 20:
            return None
        return {"with": _stats(a, sev), "without": _stats(b, sev),
                "delta_mean_pp": round(_stats(a, sev)["mean_fwd_pct"]
                                       - _stats(b, sev)["mean_fwd_pct"], 3),
                "delta_severe_pp": round(_stats(a, sev)["severe_loss_rate_pct"]
                                         - _stats(b, sev)["severe_loss_rate_pct"], 1)}
    tests = {
        "roe_rising": lambda r: (r.get("roe_trend_pp") or 0) > 0,
        "roe_accelerating": lambda r: (r.get("roe_accel_pp") or 0) > 0,
        "sales_accelerating": lambda r: (r.get("sales_growth_accel_pp") or 0) > 0,
        "leverage_falling": lambda r: (r.get("de_trend") or 0) < 0,
        "positive_surprise": lambda r: (r.get("h3_last_surprise_pct") or 0) > 0,
        "cash_conversion_gt1": lambda r: (r.get("cfo_to_net_income") or 0) > 1,
        "all_filters_passed": lambda r: r.get("n_filters_passed") == r.get(
            "n_filters_available"),
    }
    dt = {k: v for k, v in ((k, split(f, k)) for k, f in tests.items())
          if v is not None}
    # Significance + the ticker-mix control, on the same splits.
    for k, f in tests.items():
        if k not in dt:
            continue
        a = [r["fwd"] for r in rows if f(r)]
        b = [r["fwd"] for r in rows if not f(r)]
        dt[k]["mannwhitney_p_row_level"] = _mw_p(a, b)
        dt[k]["within_ticker"] = _within_ticker_delta(rows, f)
        const = _ticker_constant(rows, f)
        dt[k]["ticker_constant"] = const
        dt[k]["unit_of_analysis"] = "ticker" if const else "row"
        if const:
            tl = _ticker_level_test(rows, f)
            dt[k]["ticker_level"] = tl
            # The row-level p is not usable · it counts repeated rows of the
            # same unchanging name as independent evidence.
            dt[k]["mannwhitney_p"] = tl.get("mannwhitney_p_ticker_level")
            dt[k]["row_level_p_invalid_because"] = (
                "predicate never changes within any name · rows are not "
                "independent units")
        else:
            dt[k]["mannwhitney_p"] = dt[k]["mannwhitney_p_row_level"]
    from backend.research.evidence.abd_cohort_executor import benjamini_hochberg
    keys = sorted(dt)
    qs = benjamini_hochberg([dt[k].get("mannwhitney_p") for k in keys])
    for k, q in zip(keys, qs):
        dt[k]["bh_q"] = q
        dt[k]["significant_after_fdr"] = (q is not None and q < 0.05)
    out["dimension_tests"] = dt
    n_const = sum(1 for k in keys if dt[k].get("ticker_constant"))
    out["multiple_testing"] = {
        "n_tests": len(keys), "method": "Benjamini-Hochberg FDR at q<0.05",
        "n_significant": sum(1 for k in keys if dt[k]["significant_after_fdr"]),
        "n_tests_ticker_constant": n_const,
        "note": ("%d of %d dimensions never change within a name over this "
                 "cohort · for those, significance is computed on ticker "
                 "means, not rows" % (n_const, len(keys)))}

    # ── 7 INTERACTIONS · growth x ROE-trend x leverage ─────────────────
    inter = {}
    for r in rows:
        cell = "%s|%s|%s" % (
            "growth" if r.get("sales_growth_gt10") == 1 else "nogrowth",
            "roe_up" if (r.get("roe_trend_pp") or 0) > 0 else "roe_down",
            "lowlev" if r.get("de_lt05") == 1 else "highlev")
        inter.setdefault(cell, []).append(r)
    out["interactions"] = {k: _stats(v, sev)
                           for k, v in sorted(inter.items()) if len(v) >= 20}

    # ── THE EXCEPTION ──────────────────────────────────────────────────
    exc = {}
    for lbl, key in (("rising_but_failing", "roe_rising_but_failing"),
                     ("passing_but_falling", "roe_passing_but_falling")):
        g = [r for r in rows if r.get(key) == 1]
        if len(g) >= 15:
            exc[lbl] = _stats(g, sev)
    out["roe_exception"] = exc

    # ── 8 FAILURE STATES ───────────────────────────────────────────────
    sevs = [r for r in rows if r["fwd"] <= sev]
    if len(sevs) >= 15:
        out["failure_state_profile"] = {
            "n": len(sevs), "n_tickers": len({r["ticker"] for r in sevs}),
            "mean_filters_passed": round(
                sum(r["n_filters_passed"] for r in sevs
                    if r.get("n_filters_passed") is not None)
                / max(1, sum(1 for r in sevs
                             if r.get("n_filters_passed") is not None)), 3),
            "pct_roe_falling": round(
                sum(1 for r in sevs if (r.get("roe_trend_pp") or 0) < 0)
                / len(sevs) * 100, 1),
            "pct_sales_decelerating": round(
                sum(1 for r in sevs
                    if (r.get("sales_growth_accel_pp") or 0) < 0)
                / len(sevs) * 100, 1),
            "pct_negative_surprise": round(
                sum(1 for r in sevs
                    if (r.get("h3_last_surprise_pct") or 0) < 0)
                / len(sevs) * 100, 1)}

    # ── 10 INCREMENTAL VALUE OVER R2 · the non-negotiable final test ───
    out["incremental_over_r2"] = incremental_over_r2(rows, sev)
    return out


def analyse(root: Path, market: str) -> dict:
    per_lag = {str(l): analyse_lag(root, market, l) for l in LAGS}
    # Lag sensitivity · does any conclusion move with the assumption?
    means = {l: (v.get("population") or {}).get("mean_fwd_pct")
             for l, v in per_lag.items()}
    ns = {l: v.get("n") for l, v in per_lag.items()}
    # Population means MUST differ across lags - a longer lag admits fewer
    # rows, so it is a different sample. The question that matters is
    # whether any CONCLUSION flips, not whether the sample moved.
    keys = sorted({k for v in per_lag.values()
                   for k in (v.get("dimension_tests") or {})})
    per_dim, flipped = {}, []
    for k in keys:
        d = {l: ((v.get("dimension_tests") or {}).get(k) or {}).get("delta_mean_pp")
             for l, v in per_lag.items()}
        signs = {(1 if x > 0 else -1) for x in d.values() if x is not None}
        ok = len(signs) <= 1
        per_dim[k] = {"delta_mean_pp_by_lag": d, "sign_stable": ok}
        if not ok:
            flipped.append(k)
    stable = not flipped
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "RESEARCH ONLY · human filters are the baseline to beat",
        "market": market.lower(), "horizon": HORIZON,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filters_computed": FILTERS,
        "filters_not_computable": NOT_COMPUTABLE,
        "lag_sensitivity": {
            "lags_tested": LAGS, "n_by_lag": ns,
            "population_mean_by_lag": means,
            "note": ("a longer assumed lag admits fewer rows, so sample "
                     "statistics MUST move · only a sign flip is evidence "
                     "that a conclusion depends on the assumption"),
            "per_dimension": per_dim,
            "dimensions_that_flip_sign": flipped,
            "conclusion_stable_across_lags": stable},
        "by_lag": per_lag,
    }


def emit(root: Path, rep: dict) -> Path:
    p = (root / "reports" / "research" / "cohort"
         / f"seven_filter_ai_{rep['market']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = (root / "reports" / "research" / "cohort"
         / f"seven_filter_ai_{market.lower()}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Wave 2C seven-filter research")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = analyse(root, m)
        emit(root, rep)
        ls = rep["lag_sensitivity"]
        print(f"seven_filter:{m} · n by lag {ls['n_by_lag']} · mean fwd by lag "
              f"{ls['population_mean_by_lag']} · stable={ls['conclusion_stable_across_lags']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

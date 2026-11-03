"""PIE · chronological walk-forward over date blocks.

CEO 2026-11-03 · WHAT PIE IS BEING ASKED, PRECISELY
---------------------------------------------------
PIE does not pick stocks here. It ranks episodes R2 has ALREADY opened,
so the only question this backtest can answer is: among the names R2
entered, do the ones PIE calls P1/P2 do better than the ones it does not?

The baseline is therefore "take every episode R2 opened", not cash and
not the index. Beating the index while underperforming R2's own full set
would mean PIE destroyed value and the index comparison flattered it, so
all three are reported side by side and the R2 comparison is the one that
decides.

There is no R2 actionable baseline to beat. R2's evidence-gated classifier
returns HOLD on 228 of 228 India names (Phase 1), so a comparison against
"R2's high-conviction picks" has no population. Reported as absent rather
than substituted with the percentile path, which would be comparing PIE
against a rank.

THE FOLD RULE
-------------
Folds are blocks of consecutive ENTRY DATES, expanding. Episodes sharing
an entry date are one market observation and always land in the same
fold. Calibration and class cutoffs are fitted on the training dates only
and applied unchanged to the test dates. Nothing is shuffled, nothing is
re-quantiled on the evaluation fold, and every feature is re-checked for
lookahead on every row rather than spot-checked.

WHAT 56 DATES CAN AND CANNOT SUPPORT
------------------------------------
India has 247 episodes across 56 entry dates over three months. The
effective sample is 56, and an expanding walk-forward leaves far fewer
independent test blocks than that. This module therefore reports date
blocks next to every number and states a verdict of INSUFFICIENT EVIDENCE
unless the test blocks clear MIN_TEST_BLOCKS_FOR_VERDICT. Rows are not
evidence; that was settled in the R3 programme and is not relitigated here.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from backend.research.priority_intelligence import episode_dataset as _ds
from backend.research.priority_intelligence import features as _ft
from backend.research.priority_intelligence import scoring as _sc
from backend.research.r3_program import outcome_resolver as _res

SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.research.pie.backtest.v1"

#: Round-trip transaction cost in basis points. India delivery equity:
#: brokerage + STT + exchange charges + stamp duty + GST. Deliberately on
#: the pessimistic side; `--cost-bps` overrides.
DEFAULT_COST_BPS = 25.0

#: One-way slippage in basis points, charged on entry AND exit.
DEFAULT_SLIPPAGE_BPS = 10.0

#: Entry dates required in the first training block before any test fold.
MIN_TRAIN_DATES = 20

#: Entry dates per test block.
DEFAULT_TEST_BLOCK = 6

#: Independent test blocks required before this module will state anything
#: stronger than INSUFFICIENT EVIDENCE.
MIN_TEST_BLOCKS_FOR_VERDICT = 6

#: The benchmark index per market, as the bar files actually name it.
#: USA's S&P 500 is `_IDX_GSPC`; it is NOT `SPX`, and `usa/data/raw/us/`
#: also holds `SPXC_D1.parquet`, which is SPX Corporation - a mid-cap
#: industrial. A looser lookup would have benchmarked the S&P 500 against
#: a single industrial stock and reported a number for it.
BENCHMARK = {"india": "NSEI", "usa": "_IDX_GSPC"}

VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
VERDICT_NO_EDGE = "NO_EDGE_DETECTED"
VERDICT_EDGE = "EDGE_DETECTED"


def round_trip_cost_pct(cost_bps: float, slippage_bps: float) -> float:
    """Total drag on one completed position, in percent.

    Slippage is one-way and charged twice; the cost figure is already a
    round trip. Stated as a function so the backtest cannot quietly
    charge entry-only costs, which is the usual way a thin edge survives.
    """
    return (cost_bps + 2.0 * slippage_bps) / 100.0


def benchmark_status(root: Path, market: str) -> dict:
    """Is the benchmark series actually present and usable?

    Reported explicitly because `_bench_return` returning None for every
    row looks identical to "the index did not move" in a pooled mean. The
    first version of this module asked for `SPX` on USA, got nothing, and
    printed `benchmark n=0` without complaining.
    """
    sym = BENCHMARK.get(str(market).lower())
    bars = (None if not sym
            else _res._bars(Path(root), str(market).lower(), sym))
    if bars is None or bars.empty:
        return {"symbol": sym, "available": False, "n_bars": 0,
                "reason": "NO_BARS_FOR_BENCHMARK_SYMBOL",
                "path_pattern": _res.BARS.get(str(market).lower())}
    return {"symbol": sym, "available": True, "n_bars": int(len(bars)),
            "first_bar": str(bars.index.min().date()),
            "last_bar": str(bars.index.max().date()), "reason": None}


def _bench_return(root: Path, market: str, entry_date: str,
                  horizon: int) -> Optional[float]:
    """Index return over the same PIT window as the episode's own.

    Starts at the first index bar strictly after `entry_date`, identical
    to the convention in episode_dataset, so PIE and the benchmark are
    measured on the same clock.
    """
    sym = BENCHMARK.get(str(market).lower())
    if not sym:
        return None
    bars = _res._bars(Path(root), str(market).lower(), sym)
    if bars is None:
        return None
    w = bars[bars.index > pd.Timestamp(str(entry_date)[:10])]
    if len(w) < horizon + 1:
        return None
    a, b = float(w["close"].iloc[0]), float(w["close"].iloc[horizon])
    if a <= 0:
        return None
    return 100.0 * (b - a) / a


def build_matrix(root: Path, market: str,
                 episodes: Optional[pd.DataFrame] = None,
                 horizon: int = 20) -> pd.DataFrame:
    """One row per episode: PIT features, outcome, benchmark, availability.

    `assert_no_lookahead` runs on every row. A single leaking feature
    raises rather than being averaged away.
    """
    root = Path(root)
    mkt = str(market).lower()
    if episodes is None:
        p = _ds.episodes_path(root, mkt)
        episodes = (pd.read_parquet(p) if p.exists()
                    else _ds.build(root, mkt)[0])

    rows: List[dict] = []
    for rec in episodes.to_dict("records"):
        asof = str(rec.get("entry_date") or "")[:10]
        tk = str(rec.get("ticker") or "")
        if not asof or not tk:
            continue
        feats = _ft.all_features(root, mkt, tk, asof, episodes)
        _ft.assert_no_lookahead(feats, asof)
        av = _ft.availability(feats)
        row = {
            "episode_id": rec.get("episode_id"), "ticker": tk,
            "entry_date": asof, "market": mkt,
            "initial_signal": rec.get("initial_signal"),
            "is_closed": bool(rec.get("is_closed")),
            "closed_date": rec.get("closed_date"),
            "registry_realized_pct": rec.get("registry_realized_pct"),
            "registry_realized_resolved": bool(
                rec.get("registry_realized_resolved")),
            "n_features_available": av["n_available"],
            "max_asof_bar": av["max_asof_bar"],
        }
        for k, f in feats.items():
            row[k] = f.value
            row["%s__asof" % k] = f.asof_bar
        for h in _ds.HORIZONS:
            row["mtm_ret_%dd_pct" % h] = rec.get("mtm_ret_%dd_pct" % h)
            row["mtm_ret_%dd_resolved" % h] = bool(
                rec.get("mtm_ret_%dd_resolved" % h))
        row["bench_ret_%dd_pct" % horizon] = _bench_return(
            root, mkt, asof, horizon)
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["entry_date", "episode_id"], kind="stable"
                            ).reset_index(drop=True)
    return df


def date_blocks(dates: Sequence[str], min_train: int,
                block: int) -> List[dict]:
    """Expanding-window folds over consecutive entry dates."""
    ds = sorted(set(dates))
    folds = []
    start = min_train
    while start < len(ds):
        test = ds[start:start + block]
        if not test:
            break
        folds.append({"fold": len(folds) + 1,
                      "train_dates": ds[:start], "test_dates": test})
        start += block
    return folds


def _net(gross: Optional[float], drag: float) -> Optional[float]:
    return None if gross is None else float(gross) - drag


def _stats(vals: Sequence[float]) -> dict:
    v = [float(x) for x in vals if x is not None and x == x]
    if not v:
        return {"n": 0, "mean": None, "median": None, "win_rate": None}
    s = sorted(v)
    return {
        "n": len(v),
        "mean": round(sum(v) / len(v), 4),
        "median": round(s[len(s) // 2], 4),
        "win_rate": round(100.0 * sum(1 for x in v if x > 0) / len(v), 2),
        "min": round(s[0], 4), "max": round(s[-1], 4),
    }


def run_fold(train: pd.DataFrame, test: pd.DataFrame, *, horizon: int,
             drag: float, seed: int, fold_id: int,
             train_dates: Sequence[str],
             test_dates: Sequence[str]) -> dict:
    """Fit on train, score test, compare PIE's picks to the alternatives."""
    feat_names = list(_sc.scored_features())
    train_rows = [{**{f: r.get(f) for f in feat_names},
                   "entry_date": r.get("entry_date")}
                  for r in train.to_dict("records")]
    cal = _sc.fit(train_rows)
    cal = _sc.fit_bands(cal, train_rows)

    ret_col = "mtm_ret_%dd_pct" % horizon
    res_col = "mtm_ret_%dd_resolved" % horizon
    bench_col = "bench_ret_%dd_pct" % horizon

    scored = []
    for r in test.to_dict("records"):
        out = _sc.score_row({f: r.get(f) for f in feat_names}, cal)
        gross = r.get(ret_col) if r.get(res_col) else None
        scored.append({
            "episode_id": r.get("episode_id"), "ticker": r.get("ticker"),
            "entry_date": r.get("entry_date"),
            "pie_class": out["pie_class"], "score": out["score"],
            "available_weight": out["available_weight"],
            "abstain_reason": out["abstain_reason"],
            "dimensions": out["dimensions"],
            "gross_ret_pct": gross,
            "net_ret_pct": _net(gross, drag),
            "bench_ret_pct": r.get(bench_col),
            "registry_realized_pct": (r.get("registry_realized_pct")
                                      if r.get("registry_realized_resolved")
                                      else None),
        })

    pie_sel = [s for s in scored if s["pie_class"] in _sc.ACTIONABLE_CLASSES]
    not_sel = [s for s in scored
               if s["pie_class"] in (_sc.CLASS_WATCH, _sc.CLASS_AVOID)]
    abstained = [s for s in scored if s["pie_class"] == _sc.CLASS_ABSTAIN]

    # Baseline 1 · take every episode R2 opened in this block. This is the
    # comparison that decides, because it is the choice PIE replaces.
    all_net = [s["net_ret_pct"] for s in scored]
    # Baseline 2 · a seeded random subset of the same size, so "we picked
    # fewer names" cannot be mistaken for skill.
    rnd = random.Random(seed + fold_id)
    pool = [s for s in scored if s["net_ret_pct"] is not None]
    k = min(len(pie_sel), len(pool))
    rand_net = [s["net_ret_pct"] for s in rnd.sample(pool, k)] if k else []
    # Baseline 3 · the index over the identical window.
    bench = [s["bench_ret_pct"] for s in scored]

    pie_stats = _stats([s["net_ret_pct"] for s in pie_sel])
    all_stats = _stats(all_net)
    lift = (None if (pie_stats["mean"] is None or all_stats["mean"] is None)
            else round(pie_stats["mean"] - all_stats["mean"], 4))

    return {
        "fold": fold_id,
        "train_dates": {"n": len(train_dates), "min": train_dates[0],
                        "max": train_dates[-1]},
        "test_dates": {"n": len(test_dates), "min": test_dates[0],
                       "max": test_dates[-1]},
        "n_train_rows": len(train), "n_test_rows": len(test),
        "calibration_fingerprint": cal.fingerprint(),
        "bands": {k2: round(v, 6) for k2, v in cal.bands.items()},
        "class_counts": _sc.class_counts(scored),
        "pie_selected": pie_stats,
        "pie_not_selected": _stats([s["net_ret_pct"] for s in not_sel]),
        "abstained": {"n": len(abstained),
                      "reasons": sorted({s["abstain_reason"]
                                         for s in abstained if s["abstain_reason"]})},
        "baseline_all_r2_episodes": all_stats,
        "baseline_random_same_size": _stats(rand_net),
        "baseline_benchmark": _stats(bench),
        "lift_vs_all_r2_episodes_pp": lift,
        "rows": scored,
    }


def run(root: Path, market: str, *, horizon: int = 20,
        cost_bps: float = DEFAULT_COST_BPS,
        slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
        min_train_dates: int = MIN_TRAIN_DATES,
        test_block: int = DEFAULT_TEST_BLOCK,
        seed: int = 20261103,
        matrix: Optional[pd.DataFrame] = None) -> dict:
    """The full chronological walk-forward for one market."""
    root = Path(root)
    mkt = str(market).lower()
    df = build_matrix(root, mkt, horizon=horizon) if matrix is None else matrix
    drag = round_trip_cost_pct(cost_bps, slippage_bps)

    dates = sorted({d for d in df["entry_date"].dropna()}) if len(df) else []
    folds_spec = date_blocks(dates, min_train_dates, test_block)

    fold_reports = []
    for spec in folds_spec:
        tr = df[df["entry_date"].isin(spec["train_dates"])]
        te = df[df["entry_date"].isin(spec["test_dates"])]
        if tr.empty or te.empty:
            continue
        fold_reports.append(run_fold(
            tr, te, horizon=horizon, drag=drag, seed=seed,
            fold_id=spec["fold"], train_dates=spec["train_dates"],
            test_dates=spec["test_dates"]))

    agg = _aggregate(fold_reports, horizon)
    report = {
        "engine": ENGINE_ID, "schema_version": SCHEMA_VERSION,
        "scoring_version": _sc.SCORING_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": mkt, "horizon_days": horizon,
        "costs": {"cost_bps": cost_bps, "slippage_bps_one_way": slippage_bps,
                  "round_trip_drag_pct": drag,
                  "note": "charged once per selected position, entry and exit"},
        "population": {
            "episodes": int(len(df)),
            "entry_dates": len(dates),
            "entry_date_min": dates[0] if dates else None,
            "entry_date_max": dates[-1] if dates else None,
            "effective_sample_note": (
                "The effective sample is %d entry DATES, not %d episodes."
                % (len(dates), len(df))),
        },
        "folds_spec": {"min_train_dates": min_train_dates,
                       "test_block_dates": test_block,
                       "n_folds": len(fold_reports)},
        "r2_actionable_baseline": {
            "available": False,
            "reason": ("R2's evidence-gated classifier returns HOLD on every "
                       "name (Phase 1 · reports/diagnostics/actionable_chain_"
                       "india.json), so it has no high-conviction subset to "
                       "compare against. Its percentile path assigns actions "
                       "by rank and returns the same split on pure noise, so "
                       "it is not substituted here."),
        },
        "folds": fold_reports,
        "aggregate": agg,
    }
    # Reachability is a property of the substrate, not of a fold, so it is
    # measured against every feature the scorer would consider.
    report["abstention_reachability"] = abstention_reachability(
        df, set(_sc.scored_features()))
    report["benchmark_status"] = benchmark_status(root, mkt)
    report["dimension_attribution"] = dimension_attribution(fold_reports)
    return report


def _aggregate(folds: Sequence[dict], horizon: int) -> dict:
    """Pool test folds · and refuse a verdict the blocks cannot support."""
    if not folds:
        return {"verdict": VERDICT_INSUFFICIENT, "n_folds": 0,
                "reason": "NO_FOLDS_PRODUCED"}
    sel, allr, notsel, bench, rand = [], [], [], [], []
    for f in folds:
        for r in f["rows"]:
            if r["net_ret_pct"] is not None:
                allr.append(r["net_ret_pct"])
                if r["pie_class"] in _sc.ACTIONABLE_CLASSES:
                    sel.append(r["net_ret_pct"])
                elif r["pie_class"] in (_sc.CLASS_WATCH, _sc.CLASS_AVOID):
                    notsel.append(r["net_ret_pct"])
            if r["bench_ret_pct"] is not None:
                bench.append(r["bench_ret_pct"])
        if f["baseline_random_same_size"]["n"]:
            rand.append(f["baseline_random_same_size"]["mean"])

    s_sel, s_all = _stats(sel), _stats(allr)
    lift = (None if (s_sel["mean"] is None or s_all["mean"] is None)
            else round(s_sel["mean"] - s_all["mean"], 4))
    test_blocks = len(folds)
    n_test_dates = sum(f["test_dates"]["n"] for f in folds)

    fold_lifts = [f["lift_vs_all_r2_episodes_pp"] for f in folds
                  if f["lift_vs_all_r2_episodes_pp"] is not None]
    n_pos = sum(1 for x in fold_lifts if x > 0)

    # The gate counts blocks that produced a COMPUTABLE lift, not blocks
    # attempted. Six folds ran, but at a 20-day horizon only two of them
    # contained matured outcomes on both sides of the comparison, and
    # gating on six would have let two blocks carry a verdict.
    n_decidable = len(fold_lifts)
    if n_decidable < MIN_TEST_BLOCKS_FOR_VERDICT:
        verdict = VERDICT_INSUFFICIENT
        reason = ("%d of %d test blocks produced a computable lift · %d "
                  "required before this module will state an edge either "
                  "way. %d test entry dates over a three-month window "
                  "cannot separate a %.2fpp mean difference from noise."
                  % (n_decidable, test_blocks, MIN_TEST_BLOCKS_FOR_VERDICT,
                     n_test_dates, lift if lift is not None else 0.0))
    elif lift is None:
        verdict, reason = VERDICT_INSUFFICIENT, "NO_RESOLVED_OUTCOMES"
    elif lift > 0 and n_pos > n_decidable / 2:
        verdict = VERDICT_EDGE
        reason = ("mean lift %+.4fpp over taking every R2 episode, positive "
                  "in %d of %d decidable blocks" % (lift, n_pos, n_decidable))
    else:
        verdict = VERDICT_NO_EDGE
        reason = ("mean lift %+.4fpp over taking every R2 episode, positive "
                  "in %d of %d decidable blocks" % (lift, n_pos, n_decidable))

    return {
        "verdict": verdict, "verdict_reason": reason,
        "n_folds": test_blocks, "n_test_entry_dates": n_test_dates,
        "n_folds_with_computable_lift": len(fold_lifts),
        "min_test_blocks_for_verdict": MIN_TEST_BLOCKS_FOR_VERDICT,
        "horizon_days": horizon,
        "pie_selected_net": s_sel,
        "pie_not_selected_net": _stats(notsel),
        "all_r2_episodes_net": s_all,
        "benchmark": _stats(bench),
        "random_same_size_mean_of_fold_means": (
            round(sum(rand) / len(rand), 4) if rand else None),
        "lift_vs_all_r2_episodes_pp": lift,
        "fold_lifts_pp": fold_lifts,
        "n_folds_with_positive_lift": n_pos,
        "class_counts_pooled": {
            k: sum(f["class_counts"].get(k, 0) for f in folds)
            for k in (_sc.CLASS_P1, _sc.CLASS_P2, _sc.CLASS_WATCH,
                      _sc.CLASS_AVOID, _sc.CLASS_ABSTAIN)},
    }


def _spearman(xs, ys):
    """Rank correlation, computed without scipy.

    Ties take the average rank, which matters here because several
    dimension scores land on identical values when a fold's training grid
    is coarse.
    """
    pairs = [(x, y) for x, y in zip(xs, ys)
             if x is not None and y is not None and x == x and y == y]
    n = len(pairs)
    if n < 4:
        return None, n

    def _ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx = _ranks([p[0] for p in pairs])
    ry = _ranks([p[1] for p in pairs])
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None, n
    return round(num / (dx * dy), 4), n


def dimension_attribution(folds: Sequence[dict]) -> dict:
    """WHICH dimension carried the negative lift · descriptive only.

    PIE underperforms taking every R2 episode at every horizon in both
    markets. "Prioritisation does not work" and "these particular weights
    are wrong for this regime" are very different conclusions, and only a
    per-dimension read separates them.

    This is a DESCRIPTION, not a search. Every dimension is reported; no
    configuration is selected, promoted, or re-weighted on the strength of
    it. Running seven backtests and keeping the best would be the
    multiple-comparisons trap the R3 programme already fell into, and with
    at most 6 decidable blocks there is no power to support a choice.
    Correlations are pooled across TEST folds only, so each one is
    out-of-sample with respect to its own calibration.
    """
    per_dim = {}
    for dname in _sc.DIMENSIONS:
        xs, ys = [], []
        for f in folds:
            for r in f.get("rows") or []:
                d = (r.get("dimensions") or {}).get(dname) or {}
                if d.get("available") and r.get("net_ret_pct") is not None:
                    xs.append(d.get("score"))
                    ys.append(r["net_ret_pct"])
        rho, n = _spearman(xs, ys)
        per_dim[dname] = {
            "weight": _sc.DIMENSIONS[dname]["weight"],
            "spearman_rho_vs_net_return": rho,
            "n": n,
            "reading": ("no data" if rho is None else
                        "higher score -> higher return" if rho > 0.05 else
                        "higher score -> LOWER return" if rho < -0.05 else
                        "no monotone relation"),
        }
    total = {}
    xs, ys = [], []
    for f in folds:
        for r in f.get("rows") or []:
            if r.get("score") is not None and r.get("net_ret_pct") is not None:
                xs.append(r["score"])
                ys.append(r["net_ret_pct"])
    rho, n = _spearman(xs, ys)
    total = {"spearman_rho_vs_net_return": rho, "n": n}
    return {
        "dimensions": per_dim,
        "composite": total,
        "interpretation_note": (
            "Descriptive decomposition on insufficient data. No dimension "
            "is promoted, dropped or re-weighted from this table, and a "
            "negative rho here is not evidence that inverting the "
            "dimension would pay - that would need its own out-of-sample "
            "test on date blocks this window does not contain."),
    }


def abstention_reachability(matrix: pd.DataFrame, cal_grid_keys) -> dict:
    """Could ABSTAIN ever fire on this substrate?

    A BLOCK-severity guard that returns SKIP on every input is the bug
    class this repository has catalogued repeatedly - a gate that passes
    without opening the data. PIE's abstention deserves the same
    suspicion as any other, so its reachability is measured rather than
    assumed, and reported even when the answer is unflattering.

    Sector and fundamentals abstain structurally for every name, which
    costs 0.15 of the designed weight. The bar-derived dimensions carry
    0.70 between them and are present for every India episode, so the
    floor at 0.50 is never approached. Stated plainly: as configured,
    PIE cannot abstain on India - the same property Phase 1 criticised in
    R2's percentile classifier, reached by a different route.
    """
    weights = []
    for r in matrix.to_dict("records"):
        avail = 0.0
        for dname, spec in _sc.DIMENSIONS.items():
            for f in spec["features"]:
                v = r.get(f)
                if (isinstance(v, (int, float)) and not isinstance(v, bool)
                        and v == v and f in cal_grid_keys):
                    avail += spec["weight"]
                    break
        weights.append(round(avail, 6))
    if not weights:
        return {"reachable": None, "reason": "NO_ROWS"}
    ws = sorted(weights)
    n_below = sum(1 for w in ws if w < _sc.MIN_AVAILABLE_WEIGHT)
    return {
        "floor": _sc.MIN_AVAILABLE_WEIGHT,
        "designed_weight": round(sum(d["weight"] for d in _sc.DIMENSIONS.values()), 6),
        "available_weight_min": ws[0],
        "available_weight_median": ws[len(ws) // 2],
        "available_weight_max": ws[-1],
        "n_rows": len(ws),
        "n_rows_below_floor": n_below,
        "reachable": n_below > 0,
        "note": ("ABSTAIN fired on %d of %d rows. An abstention that never "
                 "fires is inert, and an inert guard must not be presented "
                 "as a working one." % (n_below, len(ws))),
        "structural_abstentions": dict(_ft.STRUCTURAL_ABSTENTIONS),
    }


def report_path(root: Path, market: str, horizon: int) -> Path:
    return (Path(root) / "reports" / "research" / "priority_intelligence"
            / ("backtest_%s_%dd.json" % (str(market).lower(), horizon)))


def write(root: Path, market: str, **kw) -> dict:
    horizon = kw.get("horizon", 20)
    rep = run(Path(root), market, **kw)
    p = report_path(root, market, horizon)
    p.parent.mkdir(parents=True, exist_ok=True)
    # The per-row detail is the audit trail; it goes to a sidecar so the
    # summary stays readable and the rows stay reproducible.
    rows = []
    for f in rep["folds"]:
        for r in f["rows"]:
            rows.append({"fold": f["fold"], **r})
    slim = dict(rep)
    slim["folds"] = [{k: v for k, v in f.items() if k != "rows"}
                     for f in rep["folds"]]
    p.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    if rows:
        rp = p.with_name(p.stem + "_rows.parquet")
        pd.DataFrame([{k: v for k, v in r.items() if k != "dimensions"}
                      for r in rows]).to_parquet(rp, index=False)
    rep["_written_to"] = str(p)
    return rep

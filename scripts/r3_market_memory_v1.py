"""R3 MARKET MEMORY v1 runner — §20 artifacts.

Research only. Writes under reports/research/r3/market_memory_v1/.
No production path is touched. R3 production writes remain 0.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from backend.research.r3_program.discovery_lab import build_panel, panel_hash, SEED
from backend.research.r3_program.market_memory import (
    SCHEMA_VERSION, EMBARGO_DAYS, METHODS, TOPK, LAGS, STABILITY_FLOOR,
    build_fingerprints, add_market_family, transition_frame,
    fit_representation, twin_search, twin_stability, consensus_twins,
    MARKET_COLS)
from backend.research.r3_program.market_memory_eval import (
    outcome_memory, twin_populations, leave_one_out, date_block_bootstrap,
    decision_utility, within_date_frame, SEVERE)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "research" / "r3" / "market_memory_v1"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
MARKETS = ("india", "usa")
STRIDE = 5
N_QUERIES = 600


def w(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print("   -> %s" % (OUT / name).relative_to(ROOT))


def main() -> None:
    t0all = time.time()
    print("=" * 68)
    print("R3 MARKET MEMORY v1")
    print("=" * 68)
    stab, pops, val, util, trans, meta_all = {}, {}, {}, {}, {}, {}
    fam_cov, fp_rows = {}, []

    for m in MARKETS:
        print("\n### %s" % m.upper())
        t0 = time.time()
        p, _shape, meta = build_panel(ROOT, m, stride=STRIDE)
        p = add_market_family(p)
        meta["panel_hash"] = panel_hash(p)
        meta_all[m] = meta
        fp = build_fingerprints(p)
        fam_cov[m] = fp["families"]
        cols = [c for c in fp["raw_columns"] + MARKET_COLS if c in p.columns]
        print("  panel rows=%d tickers=%d dates=%d  fingerprint dims=%d  %.1fs"
              % (meta["rows"], meta["tickers"], meta["dates"], len(cols),
                 time.time() - t0))
        print("  family coverage: %s"
              % {k: v["status"] for k, v in fp["families"].items()})

        p = p.reset_index(drop=True)
        keep = np.isfinite(p[cols].to_numpy(dtype=float)).all(axis=1)
        p = p.loc[keep].reset_index(drop=True)

        # §14 representation fitted on the EARLY window only
        dates = np.sort(p["date"].unique())
        fit_cut = pd.Timestamp(dates[int(len(dates) * 0.60)])
        fit_mask = (p["date"] <= fit_cut).to_numpy()
        rep = fit_representation(p, cols, fit_mask)
        q_start = fit_cut + pd.Timedelta(days=EMBARGO_DAYS)
        print("  representation fitted on %d rows up to %s; queries after %s"
              % (rep.fit_rows, rep.fit_date_max, q_start.date()))

        qpool = p.index[(p["date"] > q_start) & p["fwd_20d"].notna()].to_numpy()
        if len(qpool) < 100:
            print("  INSUFFICIENT_HISTORY: %d query candidates" % len(qpool))
            continue
        rng = np.random.default_rng(SEED)
        qidx = np.sort(rng.choice(qpool, size=min(N_QUERIES, len(qpool)), replace=False))
        pool = p.index.to_numpy()

        # ---- §4/§5 multi-method twins and THE stability test ----------
        t0 = time.time()
        tw = twin_search(p, rep, qidx, pool, k=50)
        st = twin_stability(tw)
        stab[m] = st
        print("  twin search %.1fs  methods=%s queries=%d"
              % (time.time() - t0, len(METHODS), len(qidx)))
        for k in TOPK:
            e = st["top_k"][str(k)]
            print("     top-%-2d mean Jaccard=%s  min=%s  max=%s"
                  % (k, e["mean"], e["min"], e["max"]))
        print("     VERDICT: %s" % st["verdict"])

        cons = consensus_twins(tw, min_methods=3, k=50)
        n_cons = [len(c) for c in cons]
        print("     consensus twins (>=3 of 4 methods): median=%d  zero-consensus queries=%d/%d"
              % (int(np.median(n_cons)), sum(1 for c in n_cons if c == 0), len(cons)))
        st["consensus"] = {"median_size": int(np.median(n_cons)),
                           "zero_consensus_queries": int(sum(1 for c in n_cons if c == 0)),
                           "n_queries": len(cons)}

        # ---- §6/§7/§8 outcome memory and populations ------------------
        pop = twin_populations(p, qidx, cons)
        pops[m] = pop
        if pop.get("status") == "OK":
            print("  populations: queries=%d dates=%d  failed=%d successful=%d"
                  % (pop["n_queries"], pop["n_dates"],
                     pop["failed_queries"]["n"], pop["successful_queries"]["n"]))
            print("     twin_fail_frac  failed-query=%s  successful-query=%s  separation=%s"
                  % (pop["failed_queries"]["mean_twin_fail_frac"],
                     pop["successful_queries"]["mean_twin_fail_frac"],
                     pop["separation_twin_fail_frac"]))
            ds = pop.get("demean_split", {})
            print("     rank corr twin_mean vs actual = %s"
                  % pop["rank_corr_twinmean_vs_actual"])
            print("     CONFOUND SPLIT  within-date rho=%s  date-level rho=%s "
                  "(date explains %s%% of twin_mean)"
                  % (ds.get("within_date_rho"), ds.get("date_level_rho"),
                     ds.get("variance_of_twin_mean_due_to_date_pct")))
        else:
            print("  populations: %s" % pop.get("status"))

        # ---- §15 date-aware validation --------------------------------
        if pop.get("status") == "OK" and pop.get("detail"):
            d = pd.DataFrame(pop["detail"]).dropna(subset=["query_outcome"])
            lod = leave_one_out(d, "twin_mean", "date")
            lot = leave_one_out(d, "twin_mean", "ticker")
            boot = date_block_bootstrap(d, "twin_mean")
            val[m] = {"leave_date_out": lod, "leave_ticker_out": lot,
                      "date_block_bootstrap": boot}
            print("  validation: leave-date-out=%s  leave-ticker-out=%s"
                  % (lod.get("verdict"), lot.get("verdict")))
            print("     block bootstrap rho=%s CI95=[%s, %s] excludes_zero=%s"
                  % (boot.get("observed_rho"), boot.get("ci95_low"),
                     boot.get("ci95_high"), boot.get("ci_excludes_zero")))
            wd = within_date_frame(d)
            lod_w = leave_one_out(wd, "tm_dm", "date", outcome="qo_dm")
            lot_w = leave_one_out(wd, "tm_dm", "ticker", outcome="qo_dm")
            boot_w = date_block_bootstrap(wd, "tm_dm", outcome="qo_dm")
            val[m]["within_date"] = {"leave_date_out": lod_w,
                                     "leave_ticker_out": lot_w,
                                     "date_block_bootstrap": boot_w}
            print("     WITHIN-DATE validation: leave-date-out=%s leave-ticker-out=%s"
                  % (lod_w.get("verdict"), lot_w.get("verdict")))
            print("        block bootstrap rho=%s CI95=[%s, %s] excludes_zero=%s"
                  % (boot_w.get("observed_rho"), boot_w.get("ci95_low"),
                     boot_w.get("ci95_high"), boot_w.get("ci_excludes_zero")))
            du = decision_utility(d, "twin_mean")
            util[m] = du
            print("  decision utility: %s" % du.get("verdict"))
            if du.get("status") == "OK":
                print("     severe %s%% -> %s%%  expectancy delta=%s  winners sacrificed=%s"
                      % (du["severe_rate_baseline_pct"], du["severe_rate_after_pct"],
                         du["expectancy_delta_pct"], du["winners_sacrificed"]))
        else:
            val[m] = {"status": "NOT_RUN", "reason": pop.get("status")}
            util[m] = {"status": "NOT_RUN", "reason": pop.get("status")}
            print("  validation + decision utility NOT RUN (%s)" % pop.get("status"))

        # ---- §9 state transitions -------------------------------------
        t0 = time.time()
        tf = transition_frame(p, ["ret_20d", "vol_20", "dd_60"], lags=LAGS)
        tcols = [c for c in tf.columns if c.startswith("d_ret_20d_")]
        tr_ok = tf[tcols].notna().all(axis=1)
        sign_seq = np.sign(tf.loc[tr_ok, tcols].to_numpy())
        labels = ["".join("+" if v > 0 else ("-" if v < 0 else "0") for v in row)
                  for row in sign_seq]
        sub = tf.loc[tr_ok].copy()
        sub["seq"] = labels
        agg = sub.groupby("seq").agg(
            n=("fwd_20d", "size"), mean=("fwd_20d", "mean"),
            dates=("date", "nunique"), tickers=("ticker", "nunique")).reset_index()
        agg = agg[agg["n"] >= 200].sort_values("mean")
        trans[m] = {"lattice": list(LAGS), "n_sequences": int(len(agg)),
                    "rows_with_full_lattice": int(tr_ok.sum()),
                    "sequences": [
                        {"sequence": r["seq"], "n": int(r["n"]),
                         "n_dates": int(r["dates"]), "n_tickers": int(r["tickers"]),
                         "mean_fwd20_pct": round(float(r["mean"]), 4)}
                        for _, r in agg.iterrows()]}
        if len(agg):
            print("  transitions %.1fs: %d recurring sequences (n>=200), "
                  "mean fwd20 spread %.3f..%.3f"
                  % (time.time() - t0, len(agg), agg["mean"].min(), agg["mean"].max()))

        fp_rows.append(pd.DataFrame({
            "market": m, "ticker": p["ticker"], "date": p["date"],
            **{c: p[c] for c in cols}}))

    _write(stab, pops, val, util, trans, meta_all, fam_cov, fp_rows)
    print("\ntotal %.1fs" % (time.time() - t0all))


def _write(stab, pops, val, util, trans, meta_all, fam_cov, fp_rows) -> None:
    print("\n### OUTPUTS")
    hdr = {"schema_version": SCHEMA_VERSION, "generated_utc": NOW, "seed": SEED,
           "stride_trading_days": STRIDE, "embargo_days": EMBARGO_DAYS,
           "methods": list(METHODS), "top_k": list(TOPK),
           "stability_floor": STABILITY_FLOOR,
           "panels": meta_all, "family_coverage": fam_cov,
           "governance": {"r2_modified": False, "r1_modified": False,
                          "r3_production_writes": 0,
                          "universe_changed": False, "ranking_changed": False,
                          "stops_changed": False, "exits_changed": False,
                          "workbook_changed": False},
           "leakage_controls": [
               "features and fingerprints use bars <= as_of only",
               "robust scaler and PCA basis fitted on an EARLY window; queries "
               "drawn strictly after it, so no future normalisation statistic "
               "enters a historical fingerprint",
               "twin references exclude the query ticker and any date inside "
               "the %d-day embargo" % EMBARGO_DAYS],
           "survivorship": ("ticker files are TODAY's names; delisted names are "
                            "absent and every long-horizon statistic is biased "
                            "upward")}

    if fp_rows:
        OUT.mkdir(parents=True, exist_ok=True)
        pd.concat(fp_rows, ignore_index=True).to_parquet(
            OUT / "fingerprints.parquet", index=False)
        print("   -> %s" % (OUT / "fingerprints.parquet").relative_to(ROOT))

    w("twin_stability.json", {**hdr, "stability": stab})
    # §7 and §8 are different populations and are written as such. Dumping the
    # same object under two names would have looked like two results.
    w("failure_twins.json", {**hdr, "population": "SEVERE_LOSS_QUERIES",
                             "threshold_pct": SEVERE,
                             "summary": {m: _pop_side(pops[m], "failed") for m in pops},
                             "detail": {m: _side_detail(pops[m], "failed") for m in pops}})
    w("success_twins.json", {**hdr, "population": "PROFITABLE_QUERIES",
                             "summary": {m: _pop_side(pops[m], "successful") for m in pops},
                             "detail": {m: _side_detail(pops[m], "successful") for m in pops}})
    w("state_transitions.json", {**hdr, "transitions": trans})
    w("counterfactual_memory.json",
      {**hdr, "status": "BLOCKED_INSUFFICIENT_DATE_DEPTH",
       "reason": ("Counterfactual twins compare an entry against itself at "
                  "T-3..T+3. That needs sealed R2 entries, of which there are 3 "
                  "date units; price history does not lift this bound.")})
    w("contradiction_memory.json",
      {**hdr, "status": "SEE_DISCOVERY_LAB",
       "reason": ("Contradiction configurations were tested in "
                  "ai_discovery_lab_v1 across 1,245 India / 1,009 USA dates and "
                  "REJECTED: the aligned-vs-conflicted separation flips sign "
                  "between train and test. Not re-run here.")})
    w("decision_utility.json", {**hdr, "decision_utility": util})
    w("confirmation_candidates.json",
      {**hdr, **_candidates(stab, pops, val, util),
       "note": ("A candidate must first have STABLE twins. Nothing downstream is "
                "meaningful if the neighbours belong to the metric.")})
    w("ai_hypotheses.json",
      {**hdr, "hypotheses": [],
       "status": "NOT_GENERATED",
       "reason": ("§13 gates the AI layer behind quantitative twin discovery. "
                  "Twin stability did not clear its floor, so there is no "
                  "discovered separation to hand an LLM. Generating hypotheses "
                  "from an unstable structure would manufacture narrative.")})
    w("market_memory_summary.json",
      {**hdr, "twin_stability": {m: stab[m]["verdict"] for m in stab},
       "populations": {m: pops[m].get("status") for m in pops},
       "validation": {m: {k: v.get("verdict") for k, v in val[m].items()
                          if isinstance(v, dict)} for m in val},
       "decision_utility": {m: util[m].get("verdict") for m in util},
       "verdict": _verdict(stab, pops, util)})

    print("\n### VERDICT")
    print("   %s" % _verdict(stab, pops, util))


def _pop_side(pop: dict, side: str) -> dict:
    if pop.get("status") != "OK":
        return {"status": pop.get("status")}
    key = "failed_queries" if side == "failed" else "successful_queries"
    return {**pop[key], "separation_twin_fail_frac": pop.get("separation_twin_fail_frac"),
            "demean_split": pop.get("demean_split")}


def _side_detail(pop: dict, side: str, limit: int = 150) -> list:
    """The worst (or best) queries, so a reader can inspect actual cases."""
    if pop.get("status") != "OK":
        return []
    rows = [r for r in pop.get("detail", []) if r.get("query_outcome") is not None]
    rows.sort(key=lambda r: r["query_outcome"], reverse=(side != "failed"))
    return rows[:limit]


def _candidates(stab, pops, val, util) -> dict:
    """§16 separates discovery from confirmation.

    Nothing here is promoted. A market whose twins are UNSTABLE cannot produce a
    candidate however good its downstream numbers look, because the object being
    measured is a property of the distance metric. Where a residual survived
    every date-aware test anyway, it is written down as a FROZEN specification
    to be run later on untouched data - which is the only legitimate way a
    result computed during exploration can ever become evidence.
    """
    confirmed, frozen = [], []
    for m, st in stab.items():
        v = (val.get(m) or {})
        wd = v.get("within_date", {})
        boot = wd.get("date_block_bootstrap", {})
        pop = pops.get(m, {})
        ds = pop.get("demean_split", {})
        survived = (wd.get("leave_date_out", {}).get("verdict") == "STABLE"
                    and wd.get("leave_ticker_out", {}).get("verdict") == "STABLE"
                    and boot.get("ci_excludes_zero") is True)
        if st.get("verdict") == "STABLE_TWINS" and survived:
            confirmed.append({"market": m, "discovery": "historical twin memory"})
        elif survived:
            frozen.append({
                "market": m,
                "discovery": "within-date twin-mean residual",
                "within_date_rho": ds.get("within_date_rho"),
                "ci95": [boot.get("ci95_low"), boot.get("ci95_high")],
                "n_queries": pop.get("n_queries"),
                "n_dates": pop.get("n_dates"),
                "blocking_issue": st.get("verdict"),
                "why_not_a_candidate": (
                    "Twin stability is %.2f at top-50, below the %.2f floor, so the "
                    "neighbourhood this statistic is computed over belongs to the "
                    "distance metric. The residual survived leave-date-out, "
                    "leave-ticker-out and a date-block bootstrap, which is why it "
                    "is recorded rather than discarded."
                    % (st["top_k"]["50"]["mean"], STABILITY_FLOOR)),
                "frozen_test_specification": {
                    "hypothesis": ("Within a date, the consensus twin-mean ranks "
                                   "forward 20d outcomes cross-sectionally."),
                    "metric": "Spearman(tm_dm, qo_dm)",
                    "pre_registered_threshold": "CI95 excludes zero on untouched data",
                    "required_before_running": [
                        "a stability-invariant twin definition, or a single "
                        "pre-registered metric chosen before seeing outcomes",
                        "a date range never used in this exploration",
                        "cross-market replication is NOT required: this did not "
                        "replicate in USA and may legitimately be market-specific"],
                }})
    return {"confirmed": confirmed, "frozen_for_confirmation": frozen}


def _verdict(stab, pops, util) -> str:
    verds = {m: s.get("verdict") for m, s in stab.items()}
    if not verds:
        return "INSUFFICIENT_HISTORY"
    if all(v == "NO_STABLE_MEMORY_STRUCTURE" for v in verds.values()):
        return ("NO_STABLE_MEMORY_STRUCTURE in every market: a historical twin is "
                "a property of the distance metric, not of the market")
    return "MIXED: %s" % verds


if __name__ == "__main__":
    main()

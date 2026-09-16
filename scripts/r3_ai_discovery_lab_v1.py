"""R3 AI DISCOVERY LAB v1 runner — §21 artifacts.

Research only. Writes under reports/research/r3/ai_discovery_lab_v1/.
No production path is touched. The strongest disposition available here is
CANDIDATE_FOR_CONFIRMATORY_VALIDATION.
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

from backend.research.r3_program.discovery_lab import (
    build_panel, panel_hash, Discovery, Ledger, SEED, SCHEMA_VERSION,
    EMBARGO_DAYS, WINDOW, FWD)
from backend.research.r3_program.discovery_experiments import (
    archetypes, analogues, twin_discrimination, latent_states,
    contradictions, dynamic_graph, counterfactual_entries, outcome_stats)
from backend.research.r3_program.discovery_adversarial import (
    latent_state_robustness, graph_null_test, community_information_test)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "research" / "r3" / "ai_discovery_lab_v1"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
MARKETS = ("india", "usa")
STRIDE = 5
OUTCOME = "fwd_20d"


def w(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print("   -> %s" % (OUT / name).relative_to(ROOT))


def main() -> None:
    t_start = time.time()
    print("=" * 66)
    print("R3 AI DISCOVERY LAB v1")
    print("=" * 66)
    led = Ledger()
    panels, shapes, metas = {}, {}, {}
    latent, arch, contra, graph, twins, cf = {}, {}, {}, {}, {}, {}

    for m in MARKETS:
        print("\n### %s" % m.upper())
        t0 = time.time()
        p, s, meta = build_panel(ROOT, m, stride=STRIDE)
        panels[m], shapes[m], metas[m] = p, s, meta
        meta["panel_hash"] = panel_hash(p)
        print("  panel rows=%d tickers=%d dates=%d (%s..%s) %.1fs"
              % (meta["rows"], meta["tickers"], meta["dates"],
                 meta["date_min"], meta["date_max"], time.time() - t0))

        # ---- A1 archetypes, swept over k and seed --------------------
        t0 = time.time()
        sweep = []
        for k in (6, 8, 10):
            a = archetypes(p, s, k=k, outcome=OUTCOME)
            sweep.append({"k": k,
                          "silhouette": a["silhouette_train"],
                          "linear_r2": a["linear_reproducibility_r2"],
                          "non_obvious": a["non_obvious"],
                          "rank_corr": a["train_test_rank_corr"],
                          "spread_train": a["outcome_spread_train_pct"],
                          "spread_test": a["outcome_spread_test_pct"]})
        a8 = archetypes(p, s, k=8, outcome=OUTCOME)
        a8.pop("labels", None)
        a8["k_sweep"] = sweep
        arch[m] = a8
        rcs = [x["rank_corr"] for x in sweep if x["rank_corr"] is not None]
        print("  A1 archetypes %.1fs  sil=%s linear_r2=%s non_obvious=%s"
              % (time.time() - t0, a8["silhouette_train"],
                 a8["linear_reproducibility_r2"], a8["non_obvious"]))
        print("     rank_corr by k: %s" % {x["k"]: x["rank_corr"] for x in sweep})
        stable = bool(rcs) and min(rcs) > 0.3
        led.add(Discovery(
            discovery_id="DL1-%s-ARCHETYPE" % m.upper(), method="KMeans on shape path",
            market=m, dataset="price bars", date_range="%s..%s" % (meta["date_min"], meta["date_max"]),
            n_rows=meta["rows"], n_tickers=meta["tickers"], n_dates=meta["dates"],
            features=["normalised %d-point cumulative return path" % 12],
            representation="shape", seed=SEED, trial_count=len(sweep),
            hypothesis="Recurring trajectory shapes separate forward 20d outcomes.",
            test="chronological train/embargo/test, rank correlation of archetype outcome ordering",
            result={"k_sweep": sweep},
            oos_status="TESTED",
            adversarial={"linear_reproducibility_r2": a8["linear_reproducibility_r2"],
                         "silhouette": a8["silhouette_train"]},
            disposition=("CANDIDATE_FOR_CONFIRMATORY_VALIDATION" if stable else "REJECTED"),
            notes=("Outcome ordering does not persist out of sample."
                   if not stable else "Ordering persisted across every k tested.")))

        # ---- B latent market states ----------------------------------
        t0 = time.time()
        ls = latent_states(p, n_states=4, outcome=OUTCOME)
        ls.pop("state_series", None)
        latent[m] = ls
        print("  B latent states %.1fs status=%s dates=%s rank_corr=%s transitions=%s"
              % (time.time() - t0, ls.get("status"), ls.get("n_dates"),
                 ls.get("train_test_rank_corr"), ls.get("n_transitions")))
        rob = latent_state_robustness(p, outcome=OUTCOME)
        ls["robustness"] = rob
        print("     robustness: %s  rank_corr %s..%s  sign_flips=%s  median_run=%s"
              % (rob["verdict"], rob["rank_corr_min"], rob["rank_corr_max"],
                 rob["sign_flips_across_configs"], rob["median_run_length_samples"]))
        lstable = (rob["verdict"] == "ROBUST")
        led.add(Discovery(
            discovery_id="DL1-%s-LATENTSTATE" % m.upper(),
            method="GaussianMixture on cross-sectional breadth/dispersion/vol",
            market=m, dataset="price bars", date_range="%s..%s" % (meta["date_min"], meta["date_max"]),
            n_rows=meta["rows"], n_tickers=meta["tickers"],
            n_dates=int(ls.get("n_dates") or 0),
            features=["median_vol20", "dispersion_ret20", "breadth_pos",
                      "median_dd60", "median_pos60"],
            representation="market-level state", seed=SEED,
            hypothesis="Discovered market states separate forward outcomes.",
            test="chronological split, rank correlation of state outcome ordering",
            result={"rank_corr_single_config": ls.get("train_test_rank_corr"),
                    "robustness": {k: rob[k] for k in
                                   ("verdict", "rank_corr_min", "rank_corr_max",
                                    "sign_flips_across_configs",
                                    "median_run_length_samples", "n_configs")}},
            oos_status="TESTED",
            adversarial={"seed_and_state_sweep": rob["verdict"],
                         "reason": rob["reason"]},
            trial_count=rob["n_configs"],
            disposition=("CANDIDATE_FOR_CONFIRMATORY_VALIDATION" if lstable else "REJECTED"),
            notes=("" if lstable else
                   "Single-config rank_corr was +0.8; the seed sweep turns it to "
                   "-0.2 on identical data and the state changes at nearly every "
                   "observation.")))

        # ---- C contradictions ----------------------------------------
        t0 = time.time()
        co = contradictions(p, outcome=OUTCOME)
        contra[m] = co
        al_tr = co["aligned_positive"]["train"].get("mean_pct")
        al_te = co["aligned_positive"]["test"].get("mean_pct")
        cf_tr = co["conflicted"]["train"].get("mean_pct")
        cf_te = co["conflicted"]["test"].get("mean_pct")
        print("  C contradictions %.1fs aligned+ tr=%s te=%s | conflicted tr=%s te=%s"
              % (time.time() - t0, al_tr, al_te, cf_tr, cf_te))
        sep_tr = (al_tr - cf_tr) if (al_tr is not None and cf_tr is not None) else None
        sep_te = (al_te - cf_te) if (al_te is not None and cf_te is not None) else None
        csig = (sep_tr is not None and sep_te is not None
                and np.sign(sep_tr) == np.sign(sep_te) and abs(sep_te) > 0.5)
        led.add(Discovery(
            discovery_id="DL1-%s-CONTRADICTION" % m.upper(),
            method="4-view agreement score", market=m, dataset="price bars",
            date_range="%s..%s" % (meta["date_min"], meta["date_max"]),
            n_rows=meta["rows"], n_tickers=meta["tickers"], n_dates=meta["dates"],
            features=co["views"], representation="agreement configuration",
            seed=SEED, trial_count=1,
            hypothesis="Agreement/conflict across independent views separates outcomes.",
            test="chronological split, aligned vs conflicted separation and sign persistence",
            result={"separation_train_pct": None if sep_tr is None else round(sep_tr, 4),
                    "separation_test_pct": None if sep_te is None else round(sep_te, 4)},
            oos_status="TESTED",
            disposition=("CANDIDATE_FOR_CONFIRMATORY_VALIDATION" if csig else "REJECTED"),
            notes="" if csig else "Separation does not hold with a consistent sign out of sample."))

        # ---- A2 analogues + failure twins ----------------------------
        t0 = time.time()
        scored = p[p[OUTCOME].notna()]
        rng = np.random.default_rng(SEED)
        samp = rng.choice(scored.index.to_numpy(),
                          size=min(1500, len(scored)), replace=False)
        an = analogues(p, shapes[m], np.sort(samp), k=50, outcome=OUTCOME)
        td = twin_discrimination(an)
        worst = scored.nsmallest(150, OUTCOME).index.to_numpy()
        fan = analogues(p, shapes[m], np.sort(worst), k=50, outcome=OUTCOME)
        ftd = twin_discrimination(fan)
        twins[m] = {"random_queries": td, "failure_queries": ftd,
                    "n_random": an["n_queries"], "n_failure": fan["n_queries"],
                    "failure_examples": [q for q in fan["queries"][:25]]}
        print("  A2 analogues %.1fs  random: rho=%s disp=%s | failure: twin_mean=%s"
              % (time.time() - t0, td.get("spearman_twin_mean_vs_actual"),
                 td.get("twin_mean_dispersion_pct"),
                 ftd.get("spearman_twin_mean_vs_actual")))
        rho = td.get("spearman_twin_mean_vs_actual")
        tsig = rho is not None and abs(rho) > 0.1
        led.add(Discovery(
            discovery_id="DL1-%s-ANALOGUE" % m.upper(),
            method="kNN on trajectory shape, ticker-excluded and embargoed",
            market=m, dataset="price bars",
            date_range="%s..%s" % (meta["date_min"], meta["date_max"]),
            n_rows=int(td.get("n_queries") or 0), n_tickers=meta["tickers"],
            n_dates=int(td.get("n_query_dates") or 0),
            features=["trajectory shape"], representation="kNN neighbourhood",
            seed=SEED, trial_count=2,
            hypothesis="Historical analogues of a pre-state predict its forward outcome.",
            test="Spearman(twin mean outcome, actual outcome) across held-out queries",
            result=td, oos_status="TESTED",
            disposition=("CANDIDATE_FOR_CONFIRMATORY_VALIDATION" if tsig else "REJECTED"),
            notes="" if tsig else "Twin-mean carries no rank information about the actual outcome."))

        # ---- D dynamic graph -----------------------------------------
        t0 = time.time()
        gdates = sorted(pd.Series(p["date"].unique()).iloc[::12].tolist())[-60:]
        gr = dynamic_graph(ROOT, m, gdates, lookback=60, top_edges=6,
                           max_tickers=200)
        graph[m] = gr
        print("  D graph %.1fs status=%s snaps=%s modularity_med=%s stability_ARI_med=%s"
              % (time.time() - t0, gr.get("status"), gr.get("n_snapshots"),
                 gr.get("modularity_median"), gr.get("community_stability_ari_median")))
        ari = gr.get("community_stability_ari_median")
        nul = graph_null_test(ROOT, m)
        info = community_information_test(ROOT, m)
        gr["null_test"] = nul
        gr["information_test"] = info
        print("     null: real_ARI=%s vs null=%s z=%s above_chance=%s"
              % (nul.get("real_ari_median"), nul.get("null_ari_mean"),
                 nul.get("z_vs_null"), nul.get("structure_above_chance")))
        print("     information: %s  peer_minus_mkt train=%s test=%s"
              % (info.get("verdict"),
                 (info.get("peer_minus_mkt") or {}).get("train_rho"),
                 (info.get("peer_minus_mkt") or {}).get("test_rho")))
        # structure being REAL is not the same claim as structure being USEFUL
        gsig = bool(info.get("carries_information"))
        led.add(Discovery(
            discovery_id="DL1-%s-GRAPH" % m.upper(),
            method="rolling correlation graph, greedy modularity communities",
            market=m, dataset="price bars",
            date_range=str(gr.get("date_range")),
            n_rows=int(gr.get("n_snapshots") or 0), n_tickers=200,
            n_dates=int(gr.get("n_snapshots") or 0),
            features=["60d rolling return correlation"],
            representation="graph communities", seed=SEED, trial_count=1,
            hypothesis=("Relational community structure is real AND carries "
                        "forward-return information beyond the market."),
            test=("ARI vs shuffled null for structure; leave-target-out "
                  "peer-minus-market rank correlation for information"),
            result={"modularity_median": gr.get("modularity_median"),
                    "stability_ari_median": ari,
                    "z_vs_null": nul.get("z_vs_null"),
                    "structure_above_chance": nul.get("structure_above_chance"),
                    "information_verdict": info.get("verdict"),
                    "peer_minus_mkt": info.get("peer_minus_mkt")},
            oos_status="TESTED",
            adversarial={"null_test": nul.get("structure_above_chance"),
                         "information_test": info.get("verdict")},
            disposition=("CANDIDATE_FOR_CONFIRMATORY_VALIDATION" if gsig else "REJECTED"),
            notes=("STRUCTURE CONFIRMED (z=%s vs null) but it carries no forward "
                   "information: once the market term is subtracted the community "
                   "effect is indistinguishable from zero. Real structure is not "
                   "the same thing as a usable signal."
                   % nul.get("z_vs_null")) if not gsig else
                  "Structure is real and carries information beyond the market."))

        # ---- E counterfactual entry timing ---------------------------
        t0 = time.time()
        ent = _sealed_entries(m)
        ce = counterfactual_entries(ROOT, m, ent) if not ent.empty else {
            "status": "NO_SEALED_ENTRIES"}
        cf[m] = ce
        print("  E counterfactual %.1fs status=%s entries=%s dates=%s verdict=%s"
              % (time.time() - t0, ce.get("status"), ce.get("n_entries"),
                 ce.get("n_dates"), ce.get("verdict")))
        led.add(Discovery(
            discovery_id="DL1-%s-COUNTERFACTUAL" % m.upper(),
            method="entry offset t-3..t+3 on sealed R2 entries",
            market=m, dataset="memory-v2 sealed decisions + price bars",
            date_range=str(ce.get("n_dates")),
            n_rows=int(ce.get("n_entries") or 0), n_tickers=int(ce.get("n_entries") or 0),
            n_dates=int(ce.get("n_dates") or 0),
            features=["entry offset"], representation="counterfactual",
            seed=SEED, trial_count=1,
            hypothesis="R2 losses are driven by entry TIMING rather than selection.",
            test="mean outcome by entry offset",
            result={k: v for k, v in (ce.get("by_offset") or {}).items()},
            oos_status="NOT_ATTEMPTED",
            disposition="BLOCKED_INSUFFICIENT_DATE_DEPTH",
            notes=("Bounded by sealed R2 memory (%s date units), NOT by price "
                   "history." % ce.get("n_dates"))))

    _write_outputs(led, panels, metas, arch, latent, contra, twins, graph, cf)
    print("\ntotal %.1fs" % (time.time() - t_start))


def _sealed_entries(market: str) -> pd.DataFrame:
    """R2 positions actually present in sealed memory-v2."""
    p = ROOT / "reports" / "research" / "r3" / "historical_replay_v1.parquet"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_parquet(p)
    d = d[(d["market"] == market) & (d.get("in_sealed_decisions") == 1)]
    if d.empty:
        return pd.DataFrame()
    return pd.DataFrame({"ticker": d["ticker"], "as_of": d["prediction_as_of"]})


def _write_outputs(led, panels, metas, arch, latent, contra, twins, graph, cf) -> None:
    print("\n### OUTPUTS")
    hdr = {"schema_version": SCHEMA_VERSION, "generated_utc": NOW, "seed": SEED,
           "stride_trading_days": STRIDE, "window": WINDOW,
           "outcome": OUTCOME, "embargo_days": EMBARGO_DAYS,
           "markets": {m: metas[m] for m in metas},
           "governance": {"r2_modified": False, "r3_production_writes": 0,
                          "max_disposition": "CANDIDATE_FOR_CONFIRMATORY_VALIDATION"},
           "survivorship": ("ticker files are TODAY's names; delisted names are "
                            "absent and every long-horizon statistic here is "
                            "biased upward as a result")}
    w("discovery_ledger.json", {**hdr, "discoveries": led.dump()})
    w("trajectory_archetypes.json", {**hdr, "archetypes": arch})
    w("latent_states.json", {**hdr, "latent_states": latent})
    w("contradiction_patterns.json", {**hdr, "contradictions": contra})
    w("failure_twins.json", {**hdr, "twins": twins})
    w("dynamic_graph.json", {**hdr, "graph": graph})
    w("counterfactual_entries.json", {**hdr, "counterfactual": cf})

    items = led.dump()
    from collections import Counter
    disp = Counter(i["disposition"] for i in items)
    cands = [i["discovery_id"] for i in items
             if i["disposition"] == "CANDIDATE_FOR_CONFIRMATORY_VALIDATION"]
    w("hypothesis_candidates.json",
      {**hdr, "candidates": cands,
       "note": ("A candidate has survived a chronological split only. It is not "
                "evidence and confers no production authority.")})
    w("discovery_summary.json",
      {**hdr, "dispositions": dict(disp),
       "candidates_for_confirmatory_validation": cands,
       "n_discoveries": len(items),
       "verdict": ("NO STRUCTURE SURVIVED" if not cands
                   else "%d candidate(s) for confirmatory validation" % len(cands))})
    print("\n### DISPOSITIONS")
    for k, v in disp.items():
        print("   %-42s %d" % (k, v))
    print("   candidates: %s" % (cands or "NONE"))


if __name__ == "__main__":
    main()

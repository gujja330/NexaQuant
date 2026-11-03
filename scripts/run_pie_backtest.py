"""CLI · PIE chronological walk-forward.

    python scripts/run_pie_backtest.py --market india --horizon 5 10 20

India is the research market. USA runs exploratory only: it has 30 entry
dates against India's 56, so its folds cannot carry a verdict and the
report says so rather than printing a number that looks like one.

Writes reports/research/priority_intelligence/backtest_<market>_<h>d.json
plus a per-row parquet audit trail. Reads price bars and the episode
dataset; writes nothing else.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.research.priority_intelligence import backtest as B  # noqa: E402


def _show(rep: dict) -> None:
    a = rep["aggregate"]
    p = rep["population"]
    print("=" * 78)
    print("PIE %s · horizon %dd · scoring %s"
          % (rep["market"].upper(), rep["horizon_days"], rep["scoring_version"]))
    print("=" * 78)
    print("  population   %d episodes · %d entry dates · %s..%s"
          % (p["episodes"], p["entry_dates"], p["entry_date_min"],
             p["entry_date_max"]))
    print("               %s" % p["effective_sample_note"])
    c = rep["costs"]
    print("  costs        %.0fbps round trip + %.0fbps slippage each way "
          "= %.2f%% drag per position"
          % (c["cost_bps"], c["slippage_bps_one_way"], c["round_trip_drag_pct"]))
    print("  folds        %d attempted · %d decidable · %d required for a verdict"
          % (a["n_folds"], a["n_folds_with_computable_lift"],
             a["min_test_blocks_for_verdict"]))

    print("\n  %-5s %-13s %-13s %5s %5s %5s %5s %7s %9s"
          % ("fold", "train", "test", "P1", "P2", "WATC", "AVOI", "actn%", "lift pp"))
    for f in rep["folds"]:
        cc = f["class_counts"]
        print("  %-5d %-13s %-13s %5d %5d %5d %5d %6.1f%% %9s"
              % (f["fold"], f["train_dates"]["max"], f["test_dates"]["max"],
                 cc["P1"], cc["P2"], cc["WATCH"], cc["AVOID"],
                 100 * cc["actionable_share"],
                 "n/a" if f["lift_vs_all_r2_episodes_pp"] is None
                 else "%+.3f" % f["lift_vs_all_r2_episodes_pp"]))

    print("\n  pooled (net of costs)")
    for k, label in (("pie_selected_net", "PIE P1+P2"),
                     ("pie_not_selected_net", "PIE declined"),
                     ("all_r2_episodes_net", "every R2 episode"),
                     ("benchmark", "benchmark index")):
        s = a[k]
        print("      %-18s n=%-4s mean=%-9s median=%-9s win=%s"
              % (label, s["n"], s["mean"], s["median"], s["win_rate"]))
    print("      %-18s %s" % ("random same size",
                              a["random_same_size_mean_of_fold_means"]))
    print("\n      lift vs every R2 episode: %s pp   (positive in %d of %d "
          "decidable blocks)"
          % (a["lift_vs_all_r2_episodes_pp"], a["n_folds_with_positive_lift"],
             a["n_folds_with_computable_lift"]))
    print("      fold lifts: %s" % a["fold_lifts_pp"])

    r2 = rep["r2_actionable_baseline"]
    print("\n  R2 actionable baseline: %s"
          % ("available" if r2["available"] else "ABSENT"))
    print("      %s" % r2["reason"])

    bs = rep["benchmark_status"]
    detail = ("available · %d bars %s..%s"
              % (bs["n_bars"], bs.get("first_bar"), bs.get("last_bar"))
              if bs["available"] else "UNAVAILABLE · %s" % bs["reason"])
    print("\n  benchmark %s: %s" % (bs["symbol"], detail))

    ar = rep["abstention_reachability"]
    print("\n  abstention reachability: %s"
          % ("REACHABLE" if ar["reachable"] else "UNREACHABLE · inert"))
    print("      available weight %.2f..%.2f against a %.2f floor · %d of %d "
          "rows below"
          % (ar["available_weight_min"], ar["available_weight_max"],
             ar["floor"], ar["n_rows_below_floor"], ar["n_rows"]))

    print("\n  VERDICT: %s" % a["verdict"])
    print("      %s" % a["verdict_reason"])
    print("\n  written: %s" % rep["_written_to"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                    default="india")
    ap.add_argument("--horizon", type=int, nargs="+", default=[5, 10, 20])
    ap.add_argument("--cost-bps", type=float, default=B.DEFAULT_COST_BPS)
    ap.add_argument("--slippage-bps", type=float,
                    default=B.DEFAULT_SLIPPAGE_BPS)
    ap.add_argument("--min-train-dates", type=int, default=B.MIN_TRAIN_DATES)
    ap.add_argument("--test-block", type=int, default=B.DEFAULT_TEST_BLOCK)
    ap.add_argument("--root", default=str(_ROOT))
    a = ap.parse_args(argv)

    markets = ("india", "usa") if a.market == "both" else (a.market,)
    for m in markets:
        for h in a.horizon:
            _show(B.write(Path(a.root), m, horizon=h, cost_bps=a.cost_bps,
                          slippage_bps=a.slippage_bps,
                          min_train_dates=a.min_train_dates,
                          test_block=a.test_block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

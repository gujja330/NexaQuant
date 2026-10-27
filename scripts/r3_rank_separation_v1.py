"""Runner · does the R2 score separate good trades from bad? Decides nothing."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.r3_program import rank_separation as rs


def main() -> int:
    for market in ("india", "usa"):
        rep = rs.run(ROOT, market)
        print("=" * 78)
        print("  %s · does the score predict forward returns?" % market.upper())
        print("=" * 78)
        print("  %-34s %6s %7s %7s %8s %9s %7s"
              % ("score @ horizon", "dates", "meanIC", "t(IC)", "IC>0%",
                 "top-next", "t"))
        for k, m in rep["results"].items():
            if m.get("error"):
                print("  %-34s %s" % (k, m["error"]))
                continue
            print("  %-34s %6d %7s %7s %7s%% %8s %7s"
                  % (k, m["n_date_units"], m["mean_ic"],
                     m["ic_t_stat_across_dates"], m["pct_dates_ic_positive"],
                     m["top_minus_next_mean_pp"], m["top_minus_next_t_stat"]))
        key = "ensemble_score@20d"
        m = rep["results"].get(key) or {}
        if not m.get("error"):
            print()
            print("  PRIMARY · %s · %d date units (%s -> %s)"
                  % (key, m["n_date_units"], m["date_range"][0],
                     m["date_range"][1]))
            print("    buckets (0 = HIGHEST score):")
            for b, v in sorted((m.get("buckets_0_is_highest_score")
                                or {}).items()):
                print("      bucket %s   mean fwd %+7.3f%%   (%d dates)"
                      % (b, v["mean_fwd_pct"], v["n_dates"]))
            print("    monotonic in score: %s" % m["monotonic_in_score"])
            print("    top beats next on %s%% of dates"
                  % m["pct_dates_top_beats_next"])
        p = rs.write(ROOT, market, rep)
        print("\n  wrote %s\n" % p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

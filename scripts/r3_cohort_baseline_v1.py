"""Runner · R2 admission-cohort outcome baseline. Decides nothing."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.r3_program import cohort_baseline as cb


def main() -> int:
    for market in ("india", "usa"):
        rep = cb.evaluate(ROOT, market)
        print("=" * 78)
        print("  %s · R2 ADMISSION COHORT (not R3 performance)" % market.upper())
        print("=" * 78)
        print("  admissions %d · unique tickers %d · dates %d · range %s"
              % (rep["n_admissions"], rep["n_unique_tickers"],
                 rep["n_admission_dates"], rep.get("date_range")))
        if rep["repeated_tickers"]:
            print("  repeated tickers: %s" % rep["repeated_tickers"])
        print()
        print("  %-5s %6s %6s %5s  %9s %9s %8s  %9s %8s"
              % ("h", "resol", "cover", "dates", "strat mean", "bench mean",
                 "ALPHA", "win%", "beat%"))
        for h in ("5", "10", "20"):
            b = rep["horizons"][h]
            s, bm, al = b["strategy"], b["benchmark"], b["alpha"]
            if not s.get("n"):
                print("  %-5s %6d %5.1f%%   --  (no resolved outcomes yet)"
                      % (h + "d", b["n_resolved"], b["coverage_pct"]))
                continue
            print("  %-5s %6d %5.1f%% %5d  %+8.3f%% %+9.3f%% %+8.3f%%  %8.1f%% %7s"
                  % (h + "d", b["n_resolved"], b["coverage_pct"],
                     b["n_admission_dates_resolved"], s["mean_pct"],
                     bm.get("mean_pct") or 0.0, al.get("mean_pct") or 0.0,
                     s["win_rate_pct"], b["beat_benchmark_pct"]))
        print()
        b = rep["horizons"]["5"]
        if b["strategy"].get("n"):
            s = b["strategy"]
            print("  5d detail · median %+.3f%% · worst %+.2f%% · best %+.2f%%"
                  % (s["median_pct"], s["worst_pct"], s["best_pct"]))
            print("            · p05 %+.2f%% · p95 %+.2f%% · sum %+.1f pp"
                  % (s["p05_pct"], s["p95_pct"], s["sum_pp"]))
            print("            · net of ASSUMED %.2f%% cost: %+.3f%%"
                  % (rep["assumed_roundtrip_cost_pct"],
                     b["net_of_assumed_cost"]["mean_pct"]))
            dl = b.get("date_level") or {}
            if dl:
                print("            · date-level mean %+.3f%% over %d dates"
                      % (dl["mean_of_date_means_pct"], dl["n_dates"]))
        dq = rep["data_quality"]
        print("  data quality · unmatched %d · dup keys %d · gaps>3bd %d"
              % (dq["unmatched_admissions_all_horizons"],
                 dq["duplicate_outcome_keys"],
                 len(dq["admission_date_gaps_over_3_business_days"])))
        for g in dq["admission_date_gaps_over_3_business_days"][:4]:
            print("      gap %s -> %s (%d business days)"
                  % (g["from"], g["to"], g["business_days"]))
        p = cb.write(ROOT, market, rep)
        print("\n  wrote %s\n" % p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

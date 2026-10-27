"""Runner · re-entry cooldown counterfactual. Writes evidence, decides nothing."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.r3_program import reentry_cooldown as rc


def main() -> int:
    for market in ("india", "usa"):
        rep = rc.run(ROOT, market)
        if rep.get("error"):
            print("%s: %s" % (market, rep["error"]))
            continue
        b = rep["baseline"]
        print("=" * 72)
        print("  %s · %d trades · %d entry dates · %d tickers"
              % (market.upper(), b["n_trades"], b["n_entry_dates"],
                 b["n_tickers"]))
        print("=" * 72)
        a = rep["sweeps"][0]["all"]
        print("  BASELINE        n=%-4d win %5.1f%%  mean %+7.3f%%  sum %+8.2f pp"
              % (a["n"], a["win_rate"], a["mean_pct"], a["sum_pp"]))
        print()
        print("  %-9s %-28s %-28s %s"
              % ("cooldown", "KEPT", "BLOCKED", "delta"))
        for s in rep["sweeps"]:
            k, bl = s["kept"], s["blocked"]
            print("  %-9s n=%-4d win %5.1f%% sum %+8.2f  n=%-4d win %5.1f%% sum %+8.2f  %+8.2f pp  dates=%d"
                  % ("%dd" % s["cooldown_days"],
                     k["n"], k["win_rate"] or 0, k["sum_pp"],
                     bl["n"], bl["win_rate"] or 0, bl["sum_pp"],
                     s["pnl_delta_pp"], s["entry_date_units_kept"]))
        p = rc.write(ROOT, market, rep)
        print("\n  wrote %s" % p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

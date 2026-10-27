"""Runner · USA 30-day candidate vs its 2026-12-31 gate. Decides nothing."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.r3_program import usa_30d_gate as g


def main() -> int:
    rep = g.run(ROOT)
    for h in ("10", "20", "30"):
        m = rep["horizons"][h]
        if m.get("error"):
            print("  %sd: %s" % (h, m["error"]))
            continue
        star = " <- PRIMARY" if h == str(g.HORIZON_DAYS) else ""
        print("  %-4s n=%-4d dates=%-3d  alpha %+6.2f%%  beat %5.1f%%  "
              "perm p=%-6s ci95=%s%s"
              % (h + "d", m["n_entries"], m["n_entry_date_units"],
                 m["mean_alpha_pct"], m["beat_index_pct"],
                 m["permutation_p_value"], m["date_block_ci95"], star))
    p = rep["primary"]
    if not p.get("error"):
        gt = p["gate"]
        print()
        print("  GATE %s   VERDICT: %s" % (gt["deadline"], gt["VERDICT"]))
        print("    date units      %d / %d%s"
              % (p["n_entry_date_units"], gt["min_date_units"],
                 ("  (short by %d)" % gt["date_units_short_by"])
                 if gt["date_units_short_by"] else "  OK"))
        print("    alpha > 0       %s" % gt["alpha_positive"])
        print("    beat > %.0f%%     %s" % (gt["min_beat_pct"],
                                            gt["beat_above_threshold"]))
        print("    CI excludes 0   %s" % gt["ci_excludes_zero"])
    out = g.write(ROOT, rep)
    print("\n  wrote %s" % out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

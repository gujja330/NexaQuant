# tools/annual_review.py
"""
AEGIS Annual Research Review — the year's executive summary, auto-generated from the Leaderboard +
registries. Not governance prose; a derived report. Run:  python tools/annual_review.py [YEAR]
"""
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
def rows(p): return list(csv.DictReader((RES / p).open())) if (RES / p).exists() else []
LB, FEAT, DS = rows("LEADERBOARD.csv"), rows("registry/FEATURE_CATALOG.csv"), rows("registry/DATASET_REGISTRY.csv")


def conf_num(s):
    try:
        return int(s.split("(")[0])
    except Exception:
        return -1


def main():
    year = sys.argv[1] if len(sys.argv) > 1 else "2026"
    yr = [r for r in LB if r["date"].startswith(year)]
    promoted = [r for r in yr if r["status"] in ("kept", "promoted")]
    rejected = [r for r in yr if r["status"] in ("not-promoted", "weak", "neutral", "no-effect", "reject-as-positive")]
    investigating = [r for r in yr if r["status"] == "investigate"]
    progs = sorted({r["program"] for r in yr})
    best = max(yr, key=lambda r: conf_num(r.get("confidence", "")), default=None)
    # success rate excludes superseded re-runs
    decided = [r for r in yr if r["status"] != "superseded"]
    rate = f"{100*len(promoted)//max(1,len(decided))}%"

    L = [f"# AEGIS Annual Research Review — {year}", "",
         "Auto-generated from the Leaderboard + registries (`python tools/annual_review.py`). The year in "
         "one page.", "",
         "| Metric | Value |", "|---|---|",
         f"| Programs active | {len(progs)} |",
         f"| Experiments logged | {len(yr)} |",
         f"| Promoted | {len(promoted)} |",
         f"| Investigating | {len(investigating)} |",
         f"| Rejected / closed | {len(rejected)} |",
         f"| Research success rate | {rate} |",
         f"| Datasets ready | {sum(1 for r in DS if r['status']=='ready')}/{len(DS)} |",
         f"| Features catalogued | {len(FEAT)} |",
         f"| Highest-confidence result | {best['factor_or_experiment']+' ('+best['confidence']+')' if best else '—'} |",
         "",
         "## Promoted this year",
         *([f"- **{r['factor_or_experiment']}** ({r['market']}, {r['cycle']}) — {r['notes'][:120]}" for r in promoted] or ["- (none — discipline over output)"]),
         "",
         "## Most surprising finding",
         "- **Static fundamentals had no cross-sectional edge** on 14y USA (Program 0): apparent 2y leads "
         "(ROE-inverse, revenue growth) were small-sample artifacts that vanished under power. The gate "
         "refused to promote them — a model rejection done right.",
         "- **The one validated edge is defensive, not offensive:** the regime overlay is cross-market "
         "(India + USA) but as RISK MANAGEMENT (drawdown reduction), not alpha.",
         "",
         "## Best / worst domains",
         "- **Best dataset:** SEC EDGAR (PIT, free) — enabled the fundamentals + earnings + insider work.",
         "- **Worst (for alpha):** static fundamental ratios — thoroughly rejected.",
         "- **Best concept:** regime overlay (defensive, cross-market). **Highest single confidence:** "
         "low-volatility selection (production both markets).",
         "",
         "## What automation bought",
         "- Every experiment auto-publishes (leaderboard + report + dashboard); leakage/PIT discipline caught "
         "TWO false positives (LGBM 0.287→0.083; the RC002 PIT-alignment bug) before they could mislead.",
         "",
         "## Going into next year",
         "- Adopt the regime overlay as the standard USA risk layer (forward-track).",
         "- Resume alternative-data domains (insider verdict pending, then analyst / ETF / 13F / macro).",
         "- AI only after multiple independent validated domains exist (today: ~1, defensive-only)."]
    out = RES / "AEGIS_ANNUAL_REVIEW.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)} · {year}: {len(yr)} experiments, {len(promoted)} promoted, rate {rate}")


if __name__ == "__main__":
    main()

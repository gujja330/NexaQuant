# india/monthly_report.py
"""
AEGIS MONTHLY OPERATIONAL REPORT — your operational history, one page per month.

Aggregates EXISTING evidence (registry · scorecard · recommendation DB · ops health) into a dated
one-pager archived under docs/monthly/. It recomputes nothing about the strategy — it is a measurement
artifact for the Operations phase, where success = trustworthy evidence accumulated, not features added.

Run:  python india/monthly_report.py            # current month
      python india/monthly_report.py 2026-06     # a specific month
"""
import sys, warnings
from datetime import date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
REG = ROOT / "data" / "aegis_registry.csv"
DB = ROOT / "data" / "aegis_recommendation_db.csv"


def _month(argv):
    for a in argv[1:]:
        if len(a) == 7 and a[4] == "-":
            return a
    return date.today().strftime("%Y-%m")


def main():
    ym = _month(sys.argv)
    from india.scorecard import load_scored, headline, rolling_12m
    r = load_scored()
    h = headline(r) if not r.empty else {}
    r12 = rolling_12m(r) if not r.empty else {}

    pub = mat = winm = medm = beat = hold = gmax = gmin = "—"
    if not r.empty:
        r["asof"] = pd.to_datetime(r["asof"]); r["mat"] = pd.to_datetime(r.get("mature_date"))
        inmo = r[r["asof"].dt.strftime("%Y-%m") == ym]
        matured = r[(r["mat"].dt.strftime("%Y-%m") == ym)]
        pub = len(inmo); mat = len(matured)
        if not matured.empty:
            ret = matured["actual_ret"]
            winm = f"{100*(ret>0).mean():.0f}%"; medm = f"{ret.median():+.1f}%"
            gmax = f"{ret.max():+.1f}%"; gmin = f"{ret.min():+.1f}%"
            hold = f"{matured['holding_days'].mean():.0f}d" if "holding_days" in matured else "—"

    runs = "—"
    if DB.exists():
        d = pd.read_csv(DB)
        runs = d[d["recommended_date"].astype(str).str.startswith(ym)]["recommended_date"].nunique() \
            if "recommended_date" in d else "—"

    L = [f"# AEGIS Monthly Report — {ym}", "",
         "## Operations", "",
         f"- Daily pipeline runs (snapshots) this month: **{runs}**",
         f"- Recommendations published this month: **{pub}**",
         f"- Recommendations matured & scored this month: **{mat}**",
         "- Operational incidents: _log manually (Yahoo outages, missing tickers, Action failures)_", "",
         "## This month's matured performance", "",
         f"- Win rate: **{winm}**  ·  Median return: **{medm}**",
         f"- Largest gain: **{gmax}**  ·  Largest loss: **{gmin}**  ·  Avg holding: **{hold}**", "",
         "## Cumulative track record (all history)", "",
         f"- Scored recs: **{h.get('scored_recs','—')}**  ·  Win rate: **{h.get('win_rate','—')}%**  ·  "
         f"Median: **{h.get('median_ret','—')}%**",
         f"- Rolling 12M win rate: **{r12.get('win_rate','—')}%**", "",
         "_Measurement only. Production frozen (AEGIS 1.x). Absolute returns survivorship-inflated; "
         "trust the relative, risk-adjusted signal._", ""]

    out = ROOT / "docs" / "monthly" / f"AEGIS_{ym}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"  Monthly report -> {out.relative_to(ROOT)}")
    print(f"  {ym}: {pub} published · {mat} matured · win {winm} · cumulative win {h.get('win_rate','—')}%")


if __name__ == "__main__":
    main()

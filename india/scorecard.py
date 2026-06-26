# india/scorecard.py
"""
LIVE EVIDENCE SCORECARD — the measurement half of the system (Feedback Loop 1).

Turns the recommendation history (the scored registry + the live recommendation DB) into a continuously
updating track record: win rate, returns, rolling 12-month form, and breakdowns by sector / regime /
holding period. This is what lets us later answer "did adding dataset X actually improve recommendations?"
— you cannot judge improvement without a stable measurement baseline. It changes METRICS, never the model.

Writes data/aegis_scorecard.csv (headline metrics) and prints a readable report.

Run: python india/scorecard.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.sectors import sector_of

REG = ROOT / "data" / "aegis_registry.csv"
DB = ROOT / "data" / "aegis_recommendation_db.csv"
OUT = ROOT / "data" / "aegis_scorecard.csv"


def load_scored():
    if not REG.exists():
        return pd.DataFrame()
    r = pd.read_csv(REG)
    r = r[(r.get("scored", 0) == 1) & (r.get("source", "") == "historical")].copy()
    if r.empty:
        return r
    r["asof"] = pd.to_datetime(r["asof"])
    r["month"] = r["asof"].dt.to_period("M")
    r["sector"] = r["symbol"].map(sector_of)
    return r


def headline(r):
    ret = r["actual_ret"]
    return {
        "scored_recs": len(r), "stocks": r["symbol"].nunique(),
        "first": str(r["asof"].min().date()), "last": str(r["asof"].max().date()),
        "win_rate": round(100 * (ret > 0).mean(), 1),
        "median_ret": round(ret.median(), 2), "avg_ret": round(ret.mean(), 2),
        "best": round(ret.max(), 1), "worst": round(ret.min(), 1),
        "hit_top25_rate": round(100 * r["hit_top25"].mean(), 1) if "hit_top25" in r else None,
    }


def rolling_12m(r):
    cutoff = r["asof"].max() - pd.DateOffset(months=12)
    last = r[r["asof"] >= cutoff]
    if last.empty:
        return {}
    return {"window_recs": len(last), "win_rate": round(100 * (last.actual_ret > 0).mean(), 1),
            "median_ret": round(last.actual_ret.median(), 2)}


def by_group(r, col, label, top=6):
    g = (r.groupby(col).agg(recs=("actual_ret", "size"),
                            win=("actual_ret", lambda x: round(100 * (x > 0).mean())),
                            median=("actual_ret", "median"), avg=("actual_ret", "mean"))
         .round(1).sort_values("avg", ascending=False))
    g = g[g["recs"] >= 5]
    return g.head(top), g.tail(3)


def live_lifecycle():
    if not DB.exists():
        return {}
    try:
        from india.recommendation_db import load_db, lifecycle
        d = lifecycle(load_db())
        return d["status"].value_counts().to_dict() if not d.empty else {}
    except Exception:
        return {}


def main():
    r = load_scored()
    print("=" * 74)
    print("  AEGIS LIVE EVIDENCE SCORECARD")
    print("=" * 74)
    if r.empty:
        print("  no scored recommendations yet."); return
    h = headline(r)
    print(f"  Track record: {h['scored_recs']} scored recs · {h['stocks']} stocks · "
          f"{h['first']} -> {h['last']}")
    print(f"  Win rate {h['win_rate']}%  ·  median {h['median_ret']:+}%  ·  avg {h['avg_ret']:+}%  "
          f"·  best {h['best']:+}%  ·  worst {h['worst']:+}%")
    rr = rolling_12m(r)
    if rr:
        print(f"  Rolling 12M: {rr['window_recs']} recs · win {rr['win_rate']}% · median {rr['median_ret']:+}%")
    lc = live_lifecycle()
    if lc:
        print("  Live lifecycle:", "  ".join(f"{k}={v}" for k, v in lc.items()))

    for col, label in [("sector", "SECTOR"), ("regime", "REGIME"), ("holding_months", "HOLDING (months)")]:
        if col not in r:
            continue
        top, bot = by_group(r, col, label)
        print(f"\n  By {label} (win% / median / avg, recs>=5):")
        for idx, row in top.iterrows():
            print(f"    {str(idx):<16} win {row['win']:>4.0f}%   median {row['median']:>+5.1f}%   "
                  f"avg {row['avg']:>+5.1f}%   ({int(row['recs'])})")

    # money: cumulative contribution leaders
    r["contrib"] = r["weight"] * r["actual_ret"]
    lead = r.groupby("symbol")["contrib"].sum().sort_values(ascending=False).round(1)
    print(f"\n  Top contributors: {', '.join(f'{s} {v:+}' for s, v in lead.head(5).items())}")
    print(f"  Worst contributors: {', '.join(f'{s} {v:+}' for s, v in lead.tail(3).items())}")

    pd.DataFrame([{**h, **{f'r12m_{k}': v for k, v in rr.items()}}]).to_csv(OUT, index=False)
    print(f"\n  Scorecard -> {OUT.relative_to(ROOT)}")
    print("  (Measurement only — this never changes the model. It is the yardstick a new dataset or")
    print("   AI model must improve, validated against the frozen v1.1 baseline.)")


if __name__ == "__main__":
    main()

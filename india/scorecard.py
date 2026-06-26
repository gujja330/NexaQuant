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
_DASH = "—"
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


def calibration(r):
    """Do the engine's implied probabilities hold up? Predicted prob for a pick = the win rate of that
    symbol's PRIOR recs (causal, what we'd have shown); compare to whether THIS rec actually won.
    Honest lens (small per-symbol samples), but it tells you if confidence is over/under-stated."""
    d = r.sort_values(["symbol", "asof"]).copy()
    d["prior_win"] = d.groupby("symbol")["actual_ret"].transform(
        lambda x: x.gt(0).shift().expanding().mean())
    d = d.dropna(subset=["prior_win"])
    if d.empty:
        return pd.DataFrame()
    b = pd.cut(d["prior_win"], [-0.01, 0.4, 0.6, 0.8, 1.01],
              labels=["<40%", "40-60%", "60-80%", "80-100%"])
    return (d.groupby(b).agg(predicted=("prior_win", "mean"),
                             actual=("actual_ret", lambda x: (x > 0).mean()),
                             n=("actual_ret", "size")).dropna())


def excursions(r, closes):
    """Decision quality: Max Favourable / Adverse Excursion — best gain and worst dip BETWEEN entry and
    exit, not just the final number. Shows how *investable* (not just eventually-right) a rec was."""
    rows = []
    for _, x in r.iterrows():
        s = x["symbol"]
        if s not in closes.columns:
            continue
        try:
            path = closes[s].loc[pd.Timestamp(x["asof"]):pd.Timestamp(x["mature_date"])].dropna()
        except Exception:
            continue
        if len(path) < 2 or path.iloc[0] <= 0:
            continue
        e = path.iloc[0]
        rows.append({"ret": float(x["actual_ret"]),
                     "mfe": 100 * (path.max() / e - 1), "mae": 100 * (path.min() / e - 1)})
    return pd.DataFrame(rows)


def quality_label(ret, mae):
    if ret >= 10 and mae > -8:
        return "Excellent"
    if ret >= 3:
        return "Good"
    if ret >= -3:
        return "Neutral"
    return "Poor"


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

    # ---- CALIBRATION: do higher implied probabilities actually win more often? ----
    extra = {}
    cal = calibration(r)
    if not cal.empty:
        print("\n  CALIBRATION (predicted win-prob vs actual, by prior-record bucket):")
        for idx, row in cal.iterrows():
            flag = "" if abs(row["predicted"] - row["actual"]) < 0.1 else "  <- miscalibrated"
            print(f"    said ~{100*row['predicted']:>4.0f}%   actual {100*row['actual']:>4.0f}%"
                  f"   ({int(row['n'])} recs){flag}")
        top = cal.iloc[-1]
        extra["calib_topbucket_gap"] = round(100 * (top["predicted"] - top["actual"]), 1)  # +ve = overconfident

    # ---- DECISION QUALITY: MFE / MAE + quality-label distribution (needs price paths) ----
    try:
        from india.feature_engine import load_panels
        closes = load_panels()[0]
        ex = excursions(r, closes)
        if not ex.empty:
            ex["label"] = [quality_label(a, b) for a, b in zip(ex["ret"], ex["mae"])]
            dist = ex["label"].value_counts(); order = ["Excellent", "Good", "Neutral", "Poor"]
            print(f"\n  DECISION QUALITY ({len(ex)} recs with price paths):")
            print(f"    Avg best gain before exit (MFE): {ex['mfe'].mean():+.1f}%   "
                  f"Avg worst dip before exit (MAE): {ex['mae'].mean():+.1f}%")
            print("    Quality: " + " · ".join(
                f"{k} {int(dist.get(k,0))} ({100*dist.get(k,0)/len(ex):.0f}%)" for k in order))
            extra.update(avg_mfe=round(ex["mfe"].mean(), 1), avg_mae=round(ex["mae"].mean(), 1),
                         pct_excellent=round(100 * dist.get("Excellent", 0) / len(ex)),
                         pct_poor=round(100 * dist.get("Poor", 0) / len(ex)))
    except Exception as e:
        print(f"  (decision-quality skipped: {type(e).__name__})")

    # money: cumulative contribution leaders
    r["contrib"] = r["weight"] * r["actual_ret"]
    lead = r.groupby("symbol")["contrib"].sum().sort_values(ascending=False).round(1)
    print(f"\n  Top contributors: {', '.join(f'{s} {v:+}' for s, v in lead.head(5).items())}")
    print(f"  Worst contributors: {', '.join(f'{s} {v:+}' for s, v in lead.tail(3).items())}")

    pd.DataFrame([{**h, **{f'r12m_{k}': v for k, v in rr.items()}, **extra}]).to_csv(OUT, index=False)
    print(f"\n  Scorecard -> {OUT.relative_to(ROOT)}")
    print("  (Measurement only — this never changes the model. It is the yardstick a new dataset or")
    print("   AI model must improve, validated against the frozen v1.1 baseline.)")


if __name__ == "__main__":
    main()

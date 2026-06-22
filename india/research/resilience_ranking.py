# india/research/resilience_ranking.py
"""
LAB EXPERIMENT (Future-2, gated): RESILIENCE RANKING.
Tests the user's Ideas 2-4 (recovery / anti-fragility / persistence) and the deep-research report's
candidate tasks 2-3, the HONEST way:

  Q1: Can resilience features predict which stocks have LOW drawdown next quarter, out-of-sample?
      (a RISK target -> should be predictable, AUC > 0.5)
  Q2: Does the full resilience set beat using TRAILING VOLATILITY ALONE? (i.e. does it add anything
      new, or just re-derive the low-vol factor ARJUNA already selects on?)
  Q3: Do resilience picks even differ from low-vol picks? (overlap of top-15 each date)

Leak-free: all features use only trailing data; label uses the FORWARD quarter; train on the older
65% of dates, test on the newer unseen 35%.

Run: python india/research/resilience_ranking.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from india.feature_engine import load_panels
from india.data_nse import NIFTY200

H = 63  # forward quarter


def maxdd(p):
    p = np.asarray(p, float)
    cm = np.maximum.accumulate(p)
    return float(((cm - p) / cm).max())


def build():
    closes, _, _, _, idx, _, _ = load_panels()
    cols = [c for c in closes.columns if c in set(NIFTY200)]
    closes = closes[cols]; rets = closes.pct_change(); ir = idx.pct_change()
    rows = []
    for i in range(252, len(closes) - H, 21):
        dt = closes.index[i]
        fdd = {s: maxdd(closes[s].iloc[i:i + H].values) for s in cols
               if not closes[s].iloc[i - 252:i + H].isna().any()}
        if len(fdd) < 30:
            continue
        idn = ir.iloc[i - 252:i]
        for s in fdd:
            r = rets[s].iloc[i - 252:i]
            c = closes[s].iloc[i - 252:i]
            vol = r.std()
            past_dd = maxdd(c.values)
            dvol = r[r < 0].std()
            below_hi = float((c < 0.95 * c.cummax()).mean())          # time spent >5% below peak
            consistency = float((c.pct_change(21).dropna() > 0).mean())
            down = idn < 0
            dbeta = (np.cov(r[down], idn[down])[0, 1] / (idn[down].var() + 1e-12)) if down.sum() > 10 else 1.0
            rows.append(dict(date=dt, sym=s, vol=vol, past_dd=past_dd, dvol=dvol,
                             below_hi=below_hi, consistency=consistency, dbeta=dbeta, fdd=fdd[s]))
    df = pd.DataFrame(rows).dropna()
    df["resilient"] = df.groupby("date")["fdd"].transform(lambda x: (x < x.median()).astype(int))
    return df


def auc_for(df, feats):
    cut = df["date"].quantile(0.65)
    tr, te = df[df.date <= cut], df[df.date > cut]
    m = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05)
    m.fit(tr[feats], tr["resilient"])
    p = m.predict_proba(te[feats])[:, 1]
    return roc_auc_score(te["resilient"], p), dict(zip(feats, m.feature_importances_))


def main():
    print("  building resilience features for Nifty-200 ...")
    df = build()
    print(f"  {df['sym'].nunique()} stocks · {df['date'].nunique()} dates · {len(df):,} samples\n")
    print("=" * 64)
    print("  RESILIENCE RANKING — does it predict forward LOW drawdown?")
    print("=" * 64)

    full = ["vol", "past_dd", "dvol", "below_hi", "consistency", "dbeta"]
    a_vol, _ = auc_for(df, ["vol"])
    a_full, imp = auc_for(df, full)
    print(f"\n  Q1/Q2  predict 'resilient next quarter' (low forward drawdown), unseen test set:")
    print(f"     trailing VOLATILITY alone : AUC {a_vol:.3f}")
    print(f"     FULL resilience feature set: AUC {a_full:.3f}")
    gain = a_full - a_vol
    print(f"     -> resilience adds {gain:+.3f} AUC over vol alone  "
          f"({'MEANINGFUL — worth pursuing' if gain > 0.02 else 'NEGLIGIBLE — just re-derives low-vol'})")
    print(f"\n  feature importance: " + "  ".join(f"{k} {100*v:.0f}%" for k, v in
          sorted(imp.items(), key=lambda x: -x[1])))

    # Q3: do resilience picks differ from low-vol picks?
    overlaps = []
    for dt, g in df.groupby("date"):
        g = g.dropna()
        if len(g) < 20:
            continue
        lowvol = set(g.nsmallest(15, "vol")["sym"])
        score = (g["past_dd"].rank() + g["dvol"].rank() + g["below_hi"].rank()
                 - g["consistency"].rank())          # lower = more resilient
        resil = set(g.assign(sc=score).nsmallest(15, "sc")["sym"])
        overlaps.append(len(lowvol & resil) / 15)
    print(f"\n  Q3  top-15 RESILIENCE picks vs top-15 LOW-VOL picks: "
          f"{100*np.mean(overlaps):.0f}% overlap on average")
    print(f"     -> {'they pick nearly the SAME stocks (no new info)' if np.mean(overlaps) > 0.6 else 'meaningfully DIFFERENT stocks (new info)'}")
    print("\n  Verdict basis: resilience is worth a portfolio A/B only if it BOTH adds AUC")
    print("  over vol AND picks different stocks. Otherwise it just rebuilds the low-vol selector.")


if __name__ == "__main__":
    main()

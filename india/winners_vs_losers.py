# india/winners_vs_losers.py
"""
WINNERS vs LOSERS — the right way to control losses: not stops (they whipsaw), but learning
what a LOSING pick looks like AT ENTRY and avoiding it at SELECTION time.

1. Take the picker's holdings (output/india_picker_log.csv = stints in the top-5, win/loss).
2. Compute the technical state AT ENTRY for each (momentum, vol, ADX, RSI, dist from 200-DMA...).
3. DESCRIPTIVE: how do winners differ from losers on each feature?  (what to avoid)
4. AI: train a winner/loser classifier (time-split) -> AUC. If it has skill, simulate dropping
   the predicted-losers and see if win-rate / avg-return improves WITHOUT gutting the count.

Run: python india/winners_vs_losers.py   (run india/picker_log.py first to make the CSV)
"""
import sys, glob, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy.smc import atr, ema
from strategy.regime import adx
from strategy.meta_label import rsi

RAW = ROOT / "data" / "raw" / "india"
LOG = ROOT / "output" / "india_picker_log.csv"


def feat_panel(df):
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    f["mom_6m"] = c.pct_change(126)
    f["mom_12m"] = c.pct_change(252)
    f["vol_60"] = c.pct_change().rolling(60).std()
    f["adx"] = adx(df, 14)
    f["rsi"] = rsi(c, 14)
    f["dist_200"] = c / c.rolling(200).mean() - 1
    f["dist_20"] = c / ema(c, 20) - 1
    return f


if not LOG.exists():
    sys.exit("Run india/picker_log.py first to create output/india_picker_log.csv")
log = pd.read_csv(LOG, parse_dates=["in_date"])
panels = {}
for fp in glob.glob(str(RAW / "*_D1.parquet")):
    s = os.path.basename(fp).replace("_D1.parquet", "")
    if s in ("SP500", "INDIAVIX", "fundamentals", "NSEBANK"):
        continue
    panels[s] = feat_panel(pd.read_parquet(fp).sort_index())

rows = []
for _, h in log.iterrows():
    p = panels.get(h["stock"])
    if p is None:
        continue
    sub = p.loc[:h["in_date"]]
    if sub.empty:
        continue
    fe = sub.iloc[-1].to_dict()
    fe["win"] = int(h["win"]); fe["ret_pct"] = h["ret_pct"]; fe["in_date"] = h["in_date"]
    rows.append(fe)
d = pd.DataFrame(rows).dropna()
feat = ["mom_6m", "mom_12m", "vol_60", "adx", "rsi", "dist_200", "dist_20"]

print("=" * 72)
print(f"  WINNERS vs LOSERS — {len(d)} holdings ({int(d['win'].sum())} win / {int((~d['win'].astype(bool)).sum())} loss)")
print("=" * 72)
print("\n  [1] DESCRIPTIVE — average feature value at ENTRY (winners vs losers):")
print(f"  {'feature':<12}{'WINNERS':>10}{'LOSERS':>10}{'diff':>10}")
for f in feat:
    wmean = d[d["win"] == 1][f].mean(); lmean = d[d["win"] == 0][f].mean()
    print(f"  {f:<12}{wmean:>10.3f}{lmean:>10.3f}{wmean-lmean:>+10.3f}")

# [2] AI classifier: can we predict winner vs loser at entry?
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
d = d.sort_values("in_date").reset_index(drop=True)
cut = int(len(d) * 0.70); tr, te = d.iloc[:cut], d.iloc[cut:]
m = HistGradientBoostingClassifier(max_depth=3, max_iter=250, learning_rate=0.05, l2_regularization=1.0, random_state=0)
m.fit(tr[feat], tr["win"]); p = m.predict_proba(te[feat])[:, 1]
auc = roc_auc_score(te["win"], p)
print(f"\n  [2] AI winner/loser classifier — TEST AUC = {auc:.3f}  "
      f"({'SKILL' if auc > 0.55 else 'weak/none'})")

# [3] filter: drop predicted-losers, compare kept vs all on the test set
print(f"\n  [3] selection filter on test holdings ({len(te)}):")
print(f"  {'keep if P(win) >=':<20}{'kept':>6}{'win%':>7}{'avg_ret%':>10}")
print(f"  {'(all, no filter)':<20}{len(te):>6}{100*te['win'].mean():>6.0f}%{te['ret_pct'].mean():>10.2f}")
for thr in (0.45, 0.50, 0.55):
    keep = p >= thr
    if keep.sum() < 5:
        continue
    sub = te[keep]
    print(f"  {thr:<20}{int(keep.sum()):>6}{100*sub['win'].mean():>6.0f}%{sub['ret_pct'].mean():>10.2f}")
print("\n  Read: if a P(win) threshold lifts win% AND avg-ret while keeping enough holdings,")
print("        the AI selection filter genuinely avoids losers (unlike stops). Else, factors win.")

# india/recommendation_registry.py
"""
RECOMMENDATION REGISTRY — the evidence database (the one thing worth building now).

Every recommendation ARJUNA ever makes is stored, then scored against what ACTUALLY happened once
its horizon elapses. After a year of forward use this holds hundreds of real observations — worth
more than another 100 backtests.

Schema (reports/recommendation_registry.csv):
  rec_id · asof · horizon_d · symbol · weight · mature_date · actual_ret · rank · universe_n
  · hit_top25 · scored · source(historical|live)

Usage:
  python india/recommendation_registry.py --backfill   # seed with historical, scored recs
  python india/recommendation_registry.py --log        # log a NEW live rec (today's champion)
  python india/recommendation_registry.py              # score any matured recs + print summary
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import select_names, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200

REG = ROOT / "reports" / "recommendation_registry.csv"
HOLD = 63
COLS = ["rec_id", "asof", "horizon_d", "symbol", "weight", "mature_date", "actual_ret",
        "rank", "universe_n", "hit_top25", "scored", "source"]


def _panels():
    c, *_ = load_panels()
    closes = c[[x for x in c.columns if x in set(NIFTY200)]]
    return closes, closes.pct_change()


def champion_picks(closes, rets, asof):
    hist = rets.loc[:asof].tail(LOOKBACK).dropna(axis=1, how="any")
    if hist.shape[1] < 20:
        return {}
    sel = select_names(hist, 15, sector_cap=2)
    w = weights_for("hrp", hist[sel]); w = w / w.sum()
    return w.to_dict()


def load_reg():
    if REG.exists():
        return pd.read_csv(REG)
    return pd.DataFrame(columns=COLS)


def log_rec(closes, rets, asof, source="live", horizon=HOLD):
    df = load_reg()
    asof = pd.Timestamp(asof)
    rid = f"{asof.date()}_{horizon}"
    if (df["rec_id"] == rid).any():
        return df, 0
    picks = champion_picks(closes, rets, asof)
    if not picks:
        return df, 0
    mature = closes.index[min(closes.index.get_loc(asof) + horizon, len(closes) - 1)]
    rows = [dict(rec_id=rid, asof=asof.date(), horizon_d=horizon, symbol=s, weight=round(w, 4),
                 mature_date=mature.date(), actual_ret=np.nan, rank=np.nan, universe_n=np.nan,
                 hit_top25=np.nan, scored=0, source=source) for s, w in picks.items()]
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    return df, len(rows)


def score(df, closes, rets):
    last = closes.index[-1]; n = 0
    for rid, g in df[df["scored"] == 0].groupby("rec_id"):
        asof = pd.Timestamp(g["asof"].iloc[0]); h = int(g["horizon_d"].iloc[0])
        i = closes.index.get_loc(asof)
        if i + h >= len(closes):
            continue                                  # not matured yet (live forward recs)
        fwd = (closes.iloc[i + h] / closes.iloc[i] - 1).dropna()
        pct = fwd.rank(pct=True); N = len(fwd)
        for idx in g.index:
            s = df.at[idx, "symbol"]
            if s in fwd.index:
                df.at[idx, "actual_ret"] = round(100 * fwd[s], 2)
                df.at[idx, "rank"] = int((1 - pct[s]) * N) + 1     # 1 = best
                df.at[idx, "universe_n"] = N
                df.at[idx, "hit_top25"] = int(pct[s] >= 0.75)
                df.at[idx, "scored"] = 1
        n += 1
    return df, n


def summary(df):
    sc = df[df["scored"] == 1]
    if sc.empty:
        print("  (no scored recommendations yet — live recs score once their horizon elapses)"); return
    for src in sc["source"].unique():
        s = sc[sc["source"] == src]
        rqs = 1 - (s["rank"] / s["universe_n"]).mean()           # 0.5 = random
        hit = 100 * s["hit_top25"].mean()
        avg_rank = s["rank"].mean(); N = int(s["universe_n"].median())
        print(f"  [{src:<10}] {s['rec_id'].nunique()} recs · {len(s)} picks · "
              f"RQS {rqs:.3f} · avg rank {avg_rank:.0f}/{N} · hit(top25) {hit:.0f}%")
    print("  RQS 0.50 = random · >0.55 = real skill. Historical = in-sample; LIVE = the real evidence.")


def main():
    closes, rets = _panels()
    df = load_reg()
    if "--backfill" in sys.argv:
        rebals = closes.index[::HOLD]
        added = 0
        for dt in rebals:
            if closes.index.get_loc(dt) + HOLD >= len(closes):
                continue
            df, k = log_rec(closes, rets, dt, source="historical")
            df.to_csv(REG, index=False); added += k
        print(f"  backfilled historical recs (+{added} picks)")
    if "--log" in sys.argv:
        df, k = log_rec(closes, rets, closes.index[-1], source="live")
        df.to_csv(REG, index=False)
        print(f"  logged LIVE rec for {closes.index[-1].date()} (+{k} picks)")
    df, scored = score(df, closes, rets)
    df.to_csv(REG, index=False)
    print(f"\n  registry: {REG.relative_to(ROOT)}  ({df['rec_id'].nunique()} recs, {scored} newly scored)")
    summary(df)


if __name__ == "__main__":
    main()

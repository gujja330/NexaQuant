# india/recommendation_registry.py
"""
RECOMMENDATION REGISTRY — the reproducible evidence database (the research/evidence layer).

Every recommendation Aegis makes is stored with enough detail to REPRODUCE it, then scored against
what actually happened once its horizon elapses. This is the machine-readable DB under reports/;
the investor-facing workbook shows only a clean view of it.

Each pick stores: fingerprint · rec_id · asof · strategy_version · universe · horizon · symbol ·
weight · buy_price · mature_date · exit_price · return% · holding days/months · rank · hit · regime.

Usage:
  python india/recommendation_registry.py --backfill   # rebuild historical, scored
  python india/recommendation_registry.py --log        # log a NEW live rec (latest date)
  python india/recommendation_registry.py              # score matured recs + summary
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
from india.config import VERSION

REG = ROOT / "reports" / "recommendation_registry.csv"
HOLD = 63
COLS = ["fingerprint", "rec_id", "asof", "strategy_version", "universe", "horizon_d", "symbol",
        "weight", "buy_price", "mature_date", "exit_price", "actual_ret", "holding_days",
        "holding_months", "rank", "universe_n", "hit_top25", "regime", "scored", "source"]
_regime_cache = None


def _panels():
    c, *_ = load_panels()
    closes = c[[x for x in c.columns if x in set(NIFTY200)]]
    return closes, closes.pct_change()


def _regime_at(asof):
    global _regime_cache
    if _regime_cache is None:
        try:
            from india.evidence.probability_matrix import regime_state_series
            _regime_cache = regime_state_series()
        except Exception:
            _regime_cache = pd.Series(dtype=object)
    try:
        return str(_regime_cache.reindex([pd.Timestamp(asof)]).iloc[0])
    except Exception:
        return ""


def champion_picks(closes, rets, asof):
    hist = rets.loc[:asof].tail(LOOKBACK).dropna(axis=1, how="any")
    if hist.shape[1] < 20:
        return {}
    sel = select_names(hist, 15, sector_cap=2)
    w = weights_for("hrp", hist[sel]); w = w / w.sum()
    return w.to_dict()


def load_reg():
    return pd.read_csv(REG) if REG.exists() else pd.DataFrame(columns=COLS)


def log_rec(closes, rets, asof, source="live", horizon=HOLD):
    df = load_reg(); asof = pd.Timestamp(asof); rid = f"{asof.date()}_{horizon}"
    if "rec_id" in df and (df["rec_id"] == rid).any():
        return df, 0
    picks = champion_picks(closes, rets, asof)
    if not picks:
        return df, 0
    i = closes.index.get_loc(asof)
    mature = closes.index[min(i + horizon, len(closes) - 1)]
    regime = _regime_at(asof); base = len(df)
    rows = []
    for j, (s, w) in enumerate(picks.items()):
        rows.append(dict(fingerprint=f"REC-{asof.strftime('%Y%m%d')}-{base + j:04d}", rec_id=rid,
            asof=asof.date(), strategy_version=VERSION, universe="nifty200", horizon_d=horizon,
            symbol=s, weight=round(w, 4), buy_price=round(float(closes.loc[asof, s]), 2),
            mature_date=mature.date(), exit_price=np.nan, actual_ret=np.nan, holding_days=horizon,
            holding_months=round(horizon / 21, 1), rank=np.nan, universe_n=np.nan, hit_top25=np.nan,
            regime=regime, scored=0, source=source))
    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True), len(rows)


def score(df, closes, rets):
    n = 0
    for rid, g in df[df["scored"] == 0].groupby("rec_id"):
        asof = pd.Timestamp(g["asof"].iloc[0]); h = int(g["horizon_d"].iloc[0])
        i = closes.index.get_loc(asof)
        if i + h >= len(closes):
            continue
        fwd = (closes.iloc[i + h] / closes.iloc[i] - 1).dropna()
        pct = fwd.rank(pct=True); N = len(fwd)
        for idx in g.index:
            s = df.at[idx, "symbol"]
            if s in fwd.index:
                df.at[idx, "exit_price"] = round(float(closes.iloc[i + h][s]), 2)
                df.at[idx, "actual_ret"] = round(100 * fwd[s], 2)
                df.at[idx, "rank"] = int((1 - pct[s]) * N) + 1
                df.at[idx, "universe_n"] = N
                df.at[idx, "hit_top25"] = int(pct[s] >= 0.75)
                df.at[idx, "scored"] = 1
        n += 1
    return df, n


def summary(df):
    sc = df[df["scored"] == 1]
    if sc.empty:
        print("  (no scored recs yet — live recs score once their horizon elapses)"); return
    for src in sc["source"].unique():
        s = sc[sc["source"] == src]
        rqs = 1 - (s["rank"] / s["universe_n"]).mean()
        print(f"  [{src:<10}] {s['rec_id'].nunique()} recs · {len(s)} picks · RQS {rqs:.3f} · "
              f"avg rank {s['rank'].mean():.0f}/{int(s['universe_n'].median())} · "
              f"hit {100*s['hit_top25'].mean():.0f}% · median ret {s['actual_ret'].median():+.1f}%")


def main():
    closes, rets = _panels(); df = load_reg()
    if "--backfill" in sys.argv:
        if REG.exists():
            REG.unlink()                              # rebuild cleanly under the enriched schema
        added = 0
        for dt in closes.index[::HOLD]:
            if closes.index.get_loc(dt) + HOLD >= len(closes):
                continue
            df, k = log_rec(closes, rets, dt, source="historical")
            df.to_csv(REG, index=False); added += k          # write each step so log_rec accumulates
        print(f"  backfilled (+{added} picks, enriched schema)")
    if "--log" in sys.argv:
        df, k = log_rec(closes, rets, closes.index[-1], source="live"); df.to_csv(REG, index=False)
        print(f"  logged LIVE rec {closes.index[-1].date()} (+{k} picks)")
    df, scored = score(df, closes, rets); df.to_csv(REG, index=False)
    print(f"\n  registry: {REG.relative_to(ROOT)}  ({df['rec_id'].nunique()} recs, {scored} newly scored)")
    summary(df)


if __name__ == "__main__":
    main()

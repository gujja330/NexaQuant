# india/run_arjuna.py
"""
ARJUNA v2 runner — generates the live (paper) portfolio from CONFIG (india/config.py).

Pipeline (config-driven): universe -> risk-based weights (Layer 3) -> regime exposure (Layer 1)
-> news blow-up filter (Layer 4) -> whole-share allocation for your capital. No real orders
(account unfunded by design until --live + funded).

  python india/run_arjuna.py                      # uses CONFIG defaults
  python india/run_arjuna.py --capital 50000 --method min_var --regime hmm
"""
import argparse, sys, warnings
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.config import CONFIG, universe_list
from india.feature_engine import load_panels
from india.arjuna_v2 import weights_for

OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)
NEWS = ROOT / "data" / "raw" / "india" / "news_sentiment.parquet"


def regime_exposure(idx, vix, asof):
    """Latest exposure multiplier (Layer 1)."""
    if CONFIG.regime == "none":
        return 1.0, "none (full)"
    if CONFIG.regime == "hmm":
        from india.regime_hmm import hmm_exposure
        e = float(hmm_exposure().reindex([asof]).iloc[0])
        return e, f"hmm ({e:.1f})"
    # simple: VIX high and/or Nifty < 200DMA
    scale, why = 1.0, []
    if vix is not None:
        thr = vix.loc[:asof].rolling(120, min_periods=30).quantile(0.80).loc[asof]
        if vix.loc[asof] > thr:
            scale *= 0.6; why.append("high-VIX")
    ma = idx.loc[:asof].rolling(200).mean().loc[asof]
    if idx.loc[asof] < ma:
        scale *= 0.6; why.append("below-200DMA")
    return scale, ("calm (full)" if not why else f"de-risk: {'+'.join(why)} -> {scale:.2f}")


def news_drop():
    if not (CONFIG.news_filter and NEWS.exists()):
        return set()
    df = pd.read_parquet(NEWS)
    latest = df.sort_values("asof").groupby("symbol").tail(1).set_index("symbol")["news_sent"]
    return set(latest[latest <= CONFIG.news_thresh].index)


def current_portfolio():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    cols = [c for c in closes.columns if c in set(universe_list())]
    closes = closes[cols]
    asof = closes.index.max()
    hist = closes.pct_change().loc[:asof].tail(CONFIG.lookback).dropna(axis=1, how="any")
    w = weights_for(CONFIG.method, hist).clip(upper=CONFIG.name_cap)
    bad = news_drop()
    excluded = [s for s in w.index if s in bad]
    if excluded:
        w = w.drop(labels=excluded)
    w = (w / w.sum()) if w.sum() > 0 else w
    deploy, regime_lbl = regime_exposure(idx, vix, asof)
    return asof, w, closes.loc[asof], deploy, regime_lbl, excluded


def allocate(weights, prices, budget):
    """Whole-share allocation toward target weights; top up leftover by highest weight affordable."""
    rows, spent = [], 0.0
    shares = {}
    for s, wt in weights.items():
        p = float(prices.get(s, np.nan))
        if not np.isfinite(p) or p <= 0:
            continue
        sh = int((budget * wt) // p)
        shares[s] = sh; spent += sh * p
    # greedy top-up with remaining cash, richest target weights first
    for s in weights.sort_values(ascending=False).index:
        p = float(prices.get(s, np.nan))
        while np.isfinite(p) and p > 0 and spent + p <= budget and (shares.get(s, 0) + 1) * p <= budget * CONFIG.name_cap * 1.5:
            shares[s] += 1; spent += p
    for s, sh in shares.items():
        if sh > 0:
            p = float(prices[s])
            rows.append({"symbol": s, "price": round(p, 1), "weight_%": round(100 * sh * p / budget, 1),
                         "shares": sh, "cost_rs": round(sh * p)})
    return pd.DataFrame(rows).sort_values("weight_%", ascending=False), spent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=CONFIG.capital)
    ap.add_argument("--method", default=CONFIG.method)
    ap.add_argument("--regime", default=CONFIG.regime)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    CONFIG.method, CONFIG.regime, CONFIG.capital = a.method, a.regime, a.capital

    asof, w, prices, deploy, regime_lbl, excluded = current_portfolio()
    invest = a.capital * deploy
    df, spent = allocate(w, prices, invest)

    print("=" * 70)
    print(f"  ARJUNA v2 portfolio  | {CONFIG.universe} | {CONFIG.method} | regime={CONFIG.regime}")
    print(f"  as of {pd.Timestamp(asof).date()}   capital Rs{a.capital:,.0f}")
    print("=" * 70)
    print(f"  regime: {regime_lbl}   investing Rs{invest:,.0f} ({100*deploy:.0f}%)")
    if excluded:
        print(f"  news filter dropped: {', '.join(excluded)}")
    if df.empty:
        print("\n  ! capital too small for whole shares of this universe."); return
    print(f"  {len(df)} holdings (risk-weighted)\n")
    print(df.to_string(index=False))
    idle = a.capital - spent
    print(f"\n  deployed Rs{spent:,.0f} ({100*spent/a.capital:.0f}%)   cash Rs{idle:,.0f} ({100*idle/a.capital:.0f}%)")

    blot = df.copy()
    blot.insert(0, "asof", pd.Timestamp(asof).date())
    blot.insert(1, "ts", datetime.now().isoformat(timespec="seconds"))
    blot.insert(2, "capital", a.capital)
    blot.to_csv(OUT / "arjuna_paper_orders.csv", index=False)
    print(f"\n  paper blotter -> {OUT / 'arjuna_paper_orders.csv'}")
    if a.live:
        print("\n  --live BLOCKED: account unfunded by design. Wire order placement after funding + cred rotation.")


if __name__ == "__main__":
    main()

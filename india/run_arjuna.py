# india/run_arjuna.py
"""
ARJUNA v1 — paper/live runner.

Generates the target portfolio for the shipped strategy (EW-30 quality + VIX de-risk) and either
PAPER-logs it (default) or, with --live, would place real orders via Angel One (guarded; the
account is unfunded by design until you finalize).

  python india/run_arjuna.py                 # paper: print the basket + Rs allocation, log a blotter
  python india/run_arjuna.py --capital 50000 # size to your capital
  python india/run_arjuna.py --live          # place real orders (BLOCKED until funded + confirmed)

Strategy recap: equal-weight 30 names by a quality+low-vol+trend screen, rebalance quarterly,
cut deployment to 50% when India VIX is in its high-fear regime. Survivorship caveat applies.
"""
import argparse, sys, warnings
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.arjuna_strategy import screen, K

OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)


def current_scores():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    score = screen(closes, vols, "quality")
    last = score.index.max()
    ranked = score.loc[last].dropna().sort_values(ascending=False)
    prices = closes.loc[last]
    deploy, regime = 1.0, "calm"
    if vix is not None:
        hi = vix.loc[last] > vix.loc[:last].rolling(120, min_periods=30).quantile(0.80).loc[last]
        if bool(hi):
            deploy, regime = 0.5, "HIGH-FEAR (deploy 50%, hold rest cash)"
    return last, ranked, prices, deploy, regime


def allocate(ranked, prices, budget, max_names=30, min_names=4):
    """Fully dynamic lot-aware allocator: pick how many names FIT the budget, drop names too
    pricey to hold without over-concentrating, then round-robin whole shares to deploy cash.
    Works for Rs10k or Rs10L. Returns a holdings DataFrame."""
    # target basket size scales with budget (~Rs3,000+ per name), clamped
    n = int(np.clip(budget // 3000, min_names, max_names))
    max_w = min(0.25, 2.0 / n)                         # per-name cap = 2x equal weight, max 25%
    cap_rs = budget * max_w
    # eligible = affordable for at least 1 share within the per-name cap, in score order
    chosen = []
    for s in ranked.index:
        p = float(prices.get(s, np.nan))
        if np.isfinite(p) and p <= cap_rs:
            chosen.append(s)
        if len(chosen) >= n:
            break
    if not chosen:                                     # budget too tiny even for the cheapest name
        return pd.DataFrame(), 0.0
    shares = {s: 0 for s in chosen}
    remaining = budget
    # round-robin: add 1 share to each name (score order) while it fits cash + weight cap
    while True:
        added = False
        for s in chosen:
            p = float(prices[s])
            if (shares[s] + 1) * p <= cap_rs and p <= remaining:
                shares[s] += 1; remaining -= p; added = True
        if not added:
            break
    rows = [{"symbol": s, "price": round(float(prices[s]), 1), "shares": shares[s],
             "cost_rs": round(shares[s] * float(prices[s])),
             "weight_%": round(100 * shares[s] * float(prices[s]) / budget, 1)}
            for s in chosen if shares[s] > 0]
    return pd.DataFrame(rows), budget - remaining


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    asof, ranked, prices, deploy, regime = current_scores()
    invest = a.capital * deploy
    df, deployed = allocate(ranked, prices, invest)

    print("=" * 66)
    print(f"  ARJUNA v1 — dynamic basket  (capital Rs{a.capital:,.0f})  as of {pd.Timestamp(asof).date()}")
    print("=" * 66)
    print(f"  VIX regime: {regime}   investable Rs{invest:,.0f} ({deploy*100:.0f}%)")
    if df.empty:
        print("\n  ! capital too small to buy even one share of an eligible name. Increase capital.")
        return
    print(f"  basket: {len(df)} names (auto-sized to capital)\n")
    print(df.to_string(index=False))
    idle = a.capital - deployed
    print(f"\n  deployed Rs{deployed:,.0f} ({100*deployed/a.capital:.0f}%)   "
          f"idle cash Rs{idle:,.0f} ({100*idle/a.capital:.0f}%)")
    if 100*idle/a.capital > 15:
        print("  (high idle cash -> capital is small for whole-share lots; more capital deploys fuller)")

    blotter = OUT / "arjuna_paper_orders.csv"
    df2 = df.copy()
    df2.insert(0, "asof", pd.Timestamp(asof).date())
    df2.insert(1, "ts", datetime.now().isoformat(timespec="seconds"))
    df2.insert(2, "capital", a.capital)
    df2.to_csv(blotter, index=False)
    print(f"\n  paper blotter saved -> {blotter}")

    if a.live:
        print("\n  --live requested, but LIVE ORDERS ARE BLOCKED: account is unfunded by design.")
        print("  When you fund + rotate credentials, we wire india/broker_angelone.py order placement here.")


if __name__ == "__main__":
    main()

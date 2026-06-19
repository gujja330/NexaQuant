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


def current_basket(n=K):
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    score = screen(closes, vols, "quality")
    last = score.index.max()
    picks = score.loc[last].dropna().sort_values(ascending=False).head(n)
    prices = closes.loc[last, picks.index]
    # VIX regime -> deployment fraction
    deploy = 1.0
    regime = "calm"
    if vix is not None:
        hi = vix.loc[last] > vix.loc[:last].rolling(120, min_periods=30).quantile(0.80).loc[last]
        if bool(hi):
            deploy, regime = 0.5, "HIGH-FEAR (deploy 50%, hold rest cash)"
    return last, picks.index.tolist(), prices, deploy, regime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--names", type=int, default=0, help="basket size; 0 = auto from capital")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    # auto-size the basket so most names are affordable (India = no fractional shares)
    n = a.names or (15 if a.capital < 200000 else 30 if a.capital < 400000 else 30)
    asof, names, prices, deploy, regime = current_basket(n)
    invest = a.capital * deploy
    per_name = invest / len(names)
    rows = []
    for s in names:
        px = float(prices[s])
        sh = int(per_name // px) if px > 0 else 0
        rows.append({"symbol": s, "price": round(px, 1), "target_rs": round(per_name),
                     "shares": sh, "cost_rs": round(sh * px)})
    df = pd.DataFrame(rows)

    print("=" * 64)
    print(f"  ARJUNA v1 — target basket as of {pd.Timestamp(asof).date()}")
    print("=" * 64)
    print(f"  capital Rs{a.capital:,.0f}   VIX regime: {regime}   deploying Rs{invest:,.0f}  ({deploy*100:.0f}%)")
    print(f"  {len(names)} names, equal weight ~Rs{per_name:,.0f} each\n")
    print(df.to_string(index=False))
    print(f"\n  total deployed: Rs{df['cost_rs'].sum():,.0f}   cash buffer: Rs{a.capital - df['cost_rs'].sum():,.0f}")

    blotter = OUT / "arjuna_paper_orders.csv"
    df.insert(0, "asof", pd.Timestamp(asof).date()); df.insert(1, "ts", datetime.now().isoformat(timespec="seconds"))
    df.to_csv(blotter, index=False)
    print(f"\n  paper blotter saved -> {blotter}")

    if a.live:
        print("\n  --live requested, but LIVE ORDERS ARE BLOCKED: account is unfunded by design.")
        print("  When you fund + rotate credentials, we wire india/broker_angelone.py order placement here.")


if __name__ == "__main__":
    main()

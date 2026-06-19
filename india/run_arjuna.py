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
from india.config import CONFIG, universe_list, apply_risk_appetite
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


def holding_projection():
    """Expected return by holding length, from the champion backtest (regime-aware net)."""
    from india.arjuna_v2 import backtest
    net, _ = backtest(CONFIG.method, regime=CONFIG.regime)
    eq = (1 + net).cumprod()
    out = {}
    for label, d in [("1 month", 21), ("3 months", 63), ("6 months", 126), ("1 year", 252)]:
        r = (eq.shift(-d) / eq - 1).dropna()
        out[label] = (r.mean(), r.quantile(0.15), r.quantile(0.85), (r > 0).mean())
    return out


def capital_profile(capital):
    """Capital -> (target positions, min Rs/position). Bigger accounts hold more names."""
    for ceil, n, mn in [(75_000, 3, 8_000), (150_000, 5, 10_000), (300_000, 8, 12_000),
                        (700_000, 10, 18_000), (2_000_000, 15, 25_000)]:
        if capital < ceil:
            return n, mn
    return 20, 30_000


def position_budget(w, prices, capital, deploy):
    """Capital-aware Position Budget Engine: positions scale with capital; deploy the FULL
    investable amount (equal-Rs base + greedy whole-share top-up so cash isn't wasted)."""
    from india.sectors import sector_of
    invest = capital * deploy
    n, _ = capital_profile(capital)
    n = max(1, n)
    picks, sec = [], {}                                 # sector<=2 (validated champion diversification)
    for s in w.nlargest(len(w)).index:
        if len(picks) >= n:
            break
        if not (np.isfinite(prices.get(s, np.nan)) and prices.get(s) > 0):
            continue
        k = sector_of(s)
        if sec.get(k, 0) >= 2:
            continue
        picks.append(s); sec[k] = sec.get(k, 0) + 1
    if not picks:
        return pd.DataFrame(), 0.0, 0
    per = invest / len(picks)
    shares = {s: int(per // float(prices[s])) for s in picks}
    spent = sum(shares[s] * float(prices[s]) for s in picks)
    # greedy top-up with leftover (cheapest affordable first) -> minimise idle cash
    while True:
        cand = [s for s in picks if spent + float(prices[s]) <= invest
                and (shares[s] + 1) * float(prices[s]) <= invest * 0.30]   # 30% per-name ceiling
        if not cand:
            break
        s = min(cand, key=lambda x: float(prices[x]))
        shares[s] += 1; spent += float(prices[s])
    rows = [{"symbol": s, "price": round(float(prices[s]), 1),
             "shares": shares[s], "cost_rs": round(shares[s] * float(prices[s])),
             "weight_%": round(100 * shares[s] * float(prices[s]) / capital, 1)}
            for s in picks if shares[s] > 0]
    df = pd.DataFrame(rows)
    return df, (df["cost_rs"].sum() if len(df) else 0.0), len(picks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=CONFIG.capital)
    ap.add_argument("--retail", action="store_true", help="Position Budget Engine: few-stock practical basket")
    ap.add_argument("--hold", default="1 year", help="planned holding period for the profit target")
    ap.add_argument("--risk", default=None, choices=["low", "medium", "high"],
                    help="risk appetite -> sets method/cap/regime")
    ap.add_argument("--method", default=None)
    ap.add_argument("--regime", default=None)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    if a.risk:                                          # risk appetite drives method/cap/regime
        CONFIG.risk_appetite = a.risk; apply_risk_appetite()
    if a.method:
        CONFIG.method = a.method
    if a.regime:
        CONFIG.regime = a.regime
    CONFIG.capital = a.capital

    asof, w, prices, deploy, regime_lbl, excluded = current_portfolio()

    if a.retail:                                        # ---- Position Budget Engine (few-stock) ----
        rdf, rspent, n = position_budget(w, prices, a.capital, deploy)
        proj = holding_projection(); avg, lo, hi, pos = proj.get(a.hold, proj["1 year"])
        hd = {"1 month": 30, "3 months": 91, "6 months": 182, "1 year": 365}.get(a.hold, 365)
        exit_d = (pd.Timestamp(asof) + pd.Timedelta(days=hd)).date()
        print("=" * 60)
        print(f"  ARJUNA RETAIL RECOMMENDATION — as on {pd.Timestamp(asof).date()}")
        print("=" * 60)
        print(f"  Capital   Rs{a.capital:,.0f}")
        print(f"  Regime    {regime_lbl}")
        print(f"  Invest    Rs{rspent:,.0f}    Cash Rs{a.capital-rspent:,.0f}")
        if rdf.empty:
            print("  Positions 0  -> regime says hold cash (or capital too small)."); return
        print(f"  Positions {len(rdf)}  (equal ~Rs{a.capital*deploy/n:,.0f} each, min Rs5,000)\n")
        for i, r in enumerate(rdf.to_dict("records"), 1):
            print(f"   {i}. {r['symbol']:<12} @Rs{r['price']:>8,.0f}  x{r['shares']:<3} = Rs{r['cost_rs']:>7,.0f}")
        print(f"\n  Hold      ~{a.hold}   (target exit ~{exit_d})")
        print(f"  Expected  {100*avg:+.1f}% backtest  /  ~{100*avg*0.65:+.1f}% realistic   "
              f"(profitable {100*pos:.0f}% of the time)")
        print("  Note: frozen Core v2.0; expectation not guaranteed; paper-trade first.")
        rblot = rdf.copy()
        for col, val in [("asof", pd.Timestamp(asof).date()), ("capital", a.capital),
                         ("hold", a.hold), ("target_exit", exit_d)]:
            rblot.insert(0, col, val)
        rblot.to_csv(OUT / "arjuna_retail_orders.csv", index=False)
        print(f"\n  saved -> output/arjuna_retail_orders.csv")
        return

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

    hold_days = {"1 month": 30, "3 months": 91, "6 months": 182, "1 year": 365}.get(a.hold, 365)
    target_exit = (pd.Timestamp(asof) + pd.Timedelta(days=hold_days)).date()
    blot = df.copy()
    blot.insert(0, "asof", pd.Timestamp(asof).date())
    blot.insert(1, "ts", datetime.now().isoformat(timespec="seconds"))
    blot.insert(2, "capital", a.capital)
    blot.insert(3, "hold", a.hold)
    blot.insert(4, "target_exit", target_exit)
    blot.to_csv(OUT / "arjuna_paper_orders.csv", index=False)

    # ---- dated recommendation with holding-period profit target ----
    proj = holding_projection()
    avg, lo, hi, pos = proj.get(a.hold, proj["1 year"])
    fwd = 0.65                                          # haircut: backtest is bull/survivorship-inflated
    print("\n" + "=" * 70)
    print(f"  RECOMMENDATION — as on {pd.Timestamp(asof).date()}")
    print("=" * 70)
    top = df.nlargest(3, "weight_%")
    print(f"  INVEST  Rs{a.capital:,.0f}  ->  Rs{spent:,.0f} across {len(df)} stocks + Rs{a.capital-spent:,.0f} cash ({regime_lbl})")
    print(f"  e.g. {', '.join(f'{r.symbol} @Rs{r.price:,.0f} x{r.shares}' for r in top.itertuples())} ...")
    print(f"  HOLD    ~{a.hold}")
    print(f"  TARGET  backtest avg {100*avg:+.1f}%  ->  Rs{a.capital*(1+avg):,.0f}   "
          f"(typical range Rs{a.capital*(1+lo):,.0f} - Rs{a.capital*(1+hi):,.0f})")
    print(f"  REALISTIC (forward, haircut)  ~{100*avg*fwd:+.1f}%  ->  ~Rs{a.capital*(1+avg*fwd):,.0f}   "
          f"profitable {100*pos:.0f}% of the time")
    print(f"  {'hold:':<8}" + "  ".join(f"{k} {100*v[0]:+.1f}%" for k, v in proj.items()))
    print("  NOTE: expectation (backtest, not guaranteed); longer hold = more reliable. Paper-trade first.")

    print(f"\n  paper blotter -> {OUT / 'arjuna_paper_orders.csv'}")
    if a.live:
        print("\n  --live BLOCKED: account unfunded by design. Wire order placement after funding + cred rotation.")


if __name__ == "__main__":
    main()

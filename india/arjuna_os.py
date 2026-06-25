# india/arjuna_os.py
"""
AEGIS OS — the Wealth Operating System (Future 3).

The leap: v1 found multibaggers, v2 managed risk, v3 manages WEALTH. Not a stock picker —
a financial planner + risk manager + portfolio manager + stock allocator in one.

  INPUT : capital, age, risk appetite, goal, horizon, emergency fund
  OUTPUT: a full multi-asset plan (Equity / Gold / Debt / Cash), with AEGIS running the
          equity sleeve (stock count from the Capital Ladder), and a blended expectation.

Asset-mix logic is transparent rule-based financial planning (age glide-path + risk + horizon).
Equity is the validated AEGIS engine. Gold CAGR is measured from data; Debt/Cash use clearly
LABELLED assumptions (FD ~7%, liquid ~3.5%) since we don't backtest those sleeves.

Run: python india/arjuna_os.py            (edit PROFILE below, or import plan())
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats
from india.capital_ladder import LADDER, rupees
from india.evidence.monte_carlo import sim

DEBT_ASSUMED = 0.070      # FD / debt fund (labelled assumption)
CASH_ASSUMED = 0.035      # liquid fund / sweep
GOLD_FALLBACK = 0.090


def gold_cagr():
    """Measured gold CAGR, HAIRCUT and capped — the raw recent figure is bull-run-inflated."""
    p = ROOT / "data/raw/india/global/GOLD.parquet"
    try:
        s = pd.read_parquet(p)["close"].dropna()
        yrs = len(s) / 252
        raw = float(s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
        return float(min(raw * 0.6, 0.09))                # honest long-run gold ~8-9% in INR
    except Exception:
        return GOLD_FALLBACK


def stocks_for(equity_amount):
    n = LADDER[0][1]
    for cap, k in LADDER:
        if equity_amount >= cap:
            n = k
    return n


def asset_mix(age, risk, horizon_years):
    """Transparent glide-path. Returns dict of weights summing to 1.0."""
    base_eq = (100 - age) / 100.0                         # standard age glide-path (65% at 35)
    base_eq *= {"low": 0.85, "medium": 1.0, "high": 1.15}.get(risk, 1.0)
    if horizon_years < 3:
        base_eq *= 0.6                                     # short goal -> protect capital
    elif horizon_years >= 10:
        base_eq *= 1.05
    eq = float(np.clip(base_eq, 0.30, 0.80))
    gold = 0.10                                            # diversifier
    cash = 0.05
    debt = max(1.0 - eq - gold - cash, 0.0)
    w = np.array([eq, gold, debt, cash]); w = w / w.sum()
    return dict(zip(["equity", "gold", "debt", "cash"], w))


def plan(capital, age, risk, goal, horizon_years, emergency_fund=0):
    mix = asset_mix(age, risk, horizon_years)
    investable = capital                                   # emergency fund is parked SEPARATELY
    eq_amt = investable * mix["equity"]
    n = stocks_for(eq_amt)

    net, idx = backtest(method="hrp", regime="global", topn=n, sector_cap=2, rebal=63)
    net = net.dropna()
    eq_stats = stats(net, idx)
    g = gold_cagr()
    # haircut the survivorship-inflated equity CAGR for an honest forward number
    eq_fwd = eq_stats["cagr"] / 100 * 0.65
    blended = (mix["equity"] * eq_fwd + mix["gold"] * g +
               mix["debt"] * DEBT_ASSUMED + mix["cash"] * CASH_ASSUMED)
    # honest expectation band + odds from Monte-Carlo on the equity sleeve (survivorship haircut)
    c, d = sim(net, 252, 0.65)
    p_pos = 100 * (c > 0).mean()
    exp_dd = 100 * float(np.median(d))
    conf = "High" if p_pos >= 90 else ("Medium" if p_pos >= 75 else "Low")
    extra = dict(p_pos=p_pos, exp_dd=exp_dd, conf=conf, eq_dd=eq_stats["dd"])
    return mix, n, eq_amt, eq_fwd, g, blended, extra


def main():
    # ---- edit your profile here ----
    PROFILE = dict(capital=10_00_000, age=35, risk="medium",
                   goal="Retirement", horizon_years=20, emergency_fund=5_00_000)

    mix, n, eq_amt, eq_fwd, g, blended, extra = plan(**PROFILE)
    cap = PROFILE["capital"]
    print("=" * 56)
    print("  AEGIS OS — WEALTH PLAN")
    print("=" * 56)
    print(f"  Capital {rupees(cap)}  ·  Age {PROFILE['age']}  ·  Risk {PROFILE['risk']}  ·  "
          f"Goal {PROFILE['goal']} ({PROFILE['horizon_years']}y)")
    if PROFILE["emergency_fund"]:
        print(f"  Emergency fund {rupees(PROFILE['emergency_fund'])} -> keep SEPARATE in liquid/FD (not invested)")
    print("  " + "-" * 52)
    print(f"  {'Sleeve':<10}{'Weight':>8}{'Amount':>14}{'Engine / assumption':>24}")
    rows = [("Equity", mix["equity"], "AEGIS " + f"({n} stocks)"),
            ("Gold", mix["gold"], f"measured {100*g:.0f}%/yr"),
            ("Debt", mix["debt"], f"assumed {100*DEBT_ASSUMED:.0f}%/yr"),
            ("Cash", mix["cash"], f"assumed {100*CASH_ASSUMED:.0f}%/yr")]
    for name, w, eng in rows:
        print(f"  {name:<10}{100*w:>7.0f}%{cap*w:>14,.0f}{eng:>24}")
    print("  " + "-" * 52)
    print(f"  Blended expected return: ~{100*blended:.1f}%/yr  =  ~Rs{cap*blended:,.0f}/yr on {rupees(cap)}")
    print(f"  (Equity uses a 35% haircut on the backtest CAGR for an honest forward figure.)")

    # ---- final, client-facing recommendation ----
    invest = cap * (mix["equity"] + mix["gold"] + mix["debt"])
    print("\n  " + "=" * 52)
    print("  FINAL RECOMMENDATION")
    print("  " + "=" * 52)
    if PROFILE["emergency_fund"]:
        print(f"  Emergency fund:     Rs{PROFILE['emergency_fund']:,.0f}  (parked separately)")
    print(f"  Invest now:         Rs{invest:,.0f}   (Equity Rs{cap*mix['equity']:,.0f} · "
          f"Gold Rs{cap*mix['gold']:,.0f} · Debt Rs{cap*mix['debt']:,.0f})")
    print(f"  Cash buffer:        Rs{cap*mix['cash']:,.0f}")
    # lead with the TRUSTWORTHY risk-side numbers (probability/drawdown), not inflated CAGR
    print(f"  P(positive, 1yr):   {extra['p_pos']:.0f}%")
    print(f"  Expected drawdown:  ~{extra['eq_dd']:.0f}% on the equity sleeve")
    print(f"  Confidence:         {extra['conf']}")
    print(f"  Review:             Quarterly")
    print(f"  (CAGR ~{100*blended-2:.0f}-{100*blended+2:.0f}% shown for reference only — "
          f"survivorship-inflated, do not rely on the level)")
    print(f"\n  Next: run  python india/run_arjuna.py --retail  for the {n}-stock equity buy-list,")
    print(f"  and  python india/confidence_engine.py  for the live regime/confidence read.")


if __name__ == "__main__":
    main()

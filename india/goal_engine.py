# india/goal_engine.py
"""
ARJUNA GOAL ENGINE (Future-3 / ARJUNA OS).

Turn a life goal into an honest savings plan:
  INPUT : goal name, years, target corpus, (optional) lump-sum already saved
  OUTPUT: required monthly SIP, expected corpus, probability of hitting the target, worst case,
          and a confidence read.

The expected return + its uncertainty come from the validated ARJUNA equity engine via Monte-Carlo
(survivorship-haircut), blended with the goal's risk posture. Longer goals lean more on equity;
short goals stay defensive. No predictions of winners — just honest compounding maths with the
real return distribution.

Run: python india/goal_engine.py        (edit GOAL below, or import plan_goal())
"""
import sys, warnings
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest
from india.evidence.monte_carlo import sim

DEBT_ASSUMED, GOLD_ASSUMED = 0.070, 0.085


def _equity_mix(years):
    """Longer horizon -> more equity. Returns (equity_w, blended_drag_from_safe_sleeves)."""
    eq = float(np.clip(0.30 + 0.05 * years, 0.30, 0.80))      # 30% short .. 80% long
    safe = 1 - eq
    safe_ret = 0.6 * DEBT_ASSUMED + 0.4 * GOLD_ASSUMED        # split of the non-equity part
    return eq, safe, safe_ret


def plan_goal(name, years, target, lump_sum=0):
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna()
    eq_w, safe_w, safe_ret = _equity_mix(years)

    # Monte-Carlo annual-return paths for the EQUITY sleeve (haircut), build blended annual returns
    cagrs, _ = sim(net, 252, 0.65)                            # 1-yr CAGR distribution, survivorship-honest
    months = int(years * 12)
    rng = np.random.default_rng(0)
    finals = []
    for _ in range(4000):
        bal = float(lump_sum)
        # draw a blended annual return each year, convert to monthly
        sip = 1.0                                            # unit SIP; we scale later
        contribs = 0.0
        yearly = rng.choice(cagrs, size=years)
        for y in range(years):
            blended = eq_w * yearly[y] + safe_w * safe_ret
            mret = (1 + blended) ** (1 / 12) - 1
            for _m in range(12):
                bal = bal * (1 + mret) + sip
                contribs += sip
        finals.append(bal)                                   # corpus per unit-monthly-SIP
    finals = np.array(finals)
    # size the SIP CONSERVATIVELY: so even a below-average (25th-percentile) path hits the target
    # -> gives ~75% probability of success, the honest way to plan a goal (not a 50/50 coin).
    safe_per_sip = np.percentile(finals, 25)
    req_sip = target / safe_per_sip
    corpora = finals * req_sip
    p_success = 100 * (corpora >= target).mean()
    worst = np.percentile(corpora, 5)
    exp_corpus = np.median(corpora)
    conf = "High" if p_success >= 75 else ("Medium" if p_success >= 55 else "Low")
    return dict(name=name, years=years, target=target, lump_sum=lump_sum, eq_w=eq_w,
                req_sip=req_sip, exp_corpus=exp_corpus, p_success=p_success, worst=worst, conf=conf)


def main():
    GOAL = dict(name="Child education", years=10, target=50_00_000, lump_sum=0)
    r = plan_goal(**GOAL)
    print("=" * 52)
    print("  ARJUNA GOAL ENGINE")
    print("=" * 52)
    print(f"  Goal:              {r['name']}")
    print(f"  Horizon:           {r['years']} years")
    print(f"  Target corpus:     Rs{r['target']:,.0f}")
    if r["lump_sum"]:
        print(f"  Lump-sum today:    Rs{r['lump_sum']:,.0f}")
    print("  " + "-" * 48)
    print(f"  Monthly SIP needed: Rs{r['req_sip']:,.0f}")
    print(f"  Equity allocation:  {100*r['eq_w']:.0f}% (rest debt/gold; horizon-based)")
    print(f"  Expected corpus:    Rs{r['exp_corpus']:,.0f}")
    print(f"  P(hit target):      {r['p_success']:.0f}%")
    print(f"  Worst case (5%):    Rs{r['worst']:,.0f}")
    print(f"  Confidence:         {r['conf']}")
    print("  " + "-" * 48)
    print("  Honest maths on the real (haircut) return distribution — not a guarantee.")
    print("  Review yearly; top up the SIP if a bad stretch puts the goal behind plan.")


if __name__ == "__main__":
    main()

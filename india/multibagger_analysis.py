# india/multibagger_analysis.py
"""
THE SBI QUESTION: can we pick the big winners (doublers) IN ADVANCE with tech+fundamentals?

1) Lists the actual multibaggers of 2021-2026 (the 'SBIs') with their multiples.
2) HONEST TEST: at the START of each year, rank all stocks by our composite screen
   (momentum + low-vol + trend + quality). Take the top-30. Then check how many of THAT
   YEAR'S actual top-10 performers were in our top-30 pick — vs what random would catch.
   If our screen catches the winners early -> picking them is real. If it catches ~random ->
   the doublers were NOT identifiable in advance (hindsight only), and concentrating is a gamble.

Run: python india/multibagger_analysis.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.arjuna_strategy import screen


def main():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    score = screen(closes, vols, "quality")

    # 1) the actual multibaggers over the whole window
    first = closes.apply(lambda c: c.dropna().iloc[0] if c.notna().any() else np.nan)
    last = closes.apply(lambda c: c.dropna().iloc[-1] if c.notna().any() else np.nan)
    mult = (last / first).dropna().sort_values(ascending=False)
    print("=" * 64)
    print("  MULTIBAGGERS 2021-2026 (the 'SBIs') — total multiple")
    print("=" * 64)
    for s, m in mult.head(15).items():
        print(f"  {s:<14} {m:>5.1f}x   (Rs1L -> Rs{m*1e5:,.0f})")
    print(f"  ... median stock: {mult.median():.1f}x")

    # 2) could our screen catch each year's top-10 winners, IN ADVANCE?
    print("\n" + "=" * 64)
    print("  CAN WE PICK THEM EARLY? our top-30 screen at year-start vs that year's top-10 winners")
    print("=" * 64)
    yrs = sorted(set(closes.index.year))
    base_hits, total_caught = [], []
    for y in yrs:
        ydates = closes.index[closes.index.year == y]
        if len(ydates) < 100:
            continue
        d0, d1 = ydates[0], ydates[-1]
        yret = (closes.loc[d1] / closes.loc[d0] - 1).dropna()
        if len(yret) < 50:
            continue
        winners = set(yret.nlargest(10).index)                 # this year's actual top-10
        srow = score.loc[:d0].iloc[-1].dropna() if d0 in score.index or len(score.loc[:d0]) else None
        if srow is None or len(srow) < 30:
            continue
        picks = set(srow.sort_values(ascending=False).head(30).index)  # our pick at year start
        caught = len(winners & picks)
        rand = 10 * 30 / len(yret)                              # expected if picking randomly
        total_caught.append(caught); base_hits.append(rand)
        names = ", ".join(list(winners & picks)[:6]) or "(none)"
        print(f"  {y}: caught {caught}/10 of the winners early (random would catch ~{rand:.1f})   {names}")
    if total_caught:
        print("  " + "-" * 58)
        print(f"  AVG: our screen caught {np.mean(total_caught):.1f}/10 early   "
              f"random ~{np.mean(base_hits):.1f}/10")
        verdict = ("SKILL: screen catches winners early -> picking is real" if np.mean(total_caught) > np.mean(base_hits) + 1
                   else "NO SKILL: ~random -> the doublers were NOT identifiable in advance")
        print(f"  VERDICT: {verdict}")


if __name__ == "__main__":
    main()

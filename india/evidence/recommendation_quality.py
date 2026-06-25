# india/evidence/recommendation_quality.py
"""
TRACK C — VALIDATION FRAMEWORK: the Dataset/Method Scorecard.

Measures the thing users actually care about — RECOMMENDATION QUALITY — not Sharpe:
  RQS (Recommendation Quality Score): average forward-return PERCENTILE of the picks.
        0.50 = no skill (random); >0.50 = picks finish above the universe median.
  Hit Rate: % of picks that finish in the TOP QUARTILE over the horizon.
  Avg rank: average finishing rank out of N (lower = better), the intuitive version.
  IC: Spearman of the factor score vs forward return.

Bake-off vs STANDARD FACTORS (not just random): Random · Momentum · Quality(risk-adj) · Low-Vol ·
Alpha(composite). Answers "does ARJUNA beat standard factor investing?" — and gives the template
every NEW dataset must pass (same pipeline: features -> IC -> RQS/Hit -> OOS -> forward paper).

NOTE: true Quality/Value factors need POINT-IN-TIME fundamentals we don't have causally — so only
price-derivable proxies are tested here. That gap is itself evidence for why PIT data is dataset #1.

Run: python india/evidence/recommendation_quality.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from scipy.stats import spearmanr
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import sector_of

REBAL, LOOK, HOLD, TOPN = 21, 120, 63, 20      # monthly sample, 6m features, 3m horizon, top-20
closes = rets = None


def _load():
    global closes, rets
    c, _, _, _, _, _, _ = load_panels()
    closes = c[[x for x in c.columns if x in set(NIFTY200)]]
    rets = closes.pct_change()


def scores(dt, cols):
    """Causal factor scores (higher = more attractive) for each method."""
    px = closes.loc[:dt]
    mom = (px.iloc[-1] / px.iloc[-127] - 1).reindex(cols)
    vol = rets.loc[:dt].tail(LOOK).std().reindex(cols)
    inv_vol = 1.0 / vol
    quality = mom / vol                                   # risk-adjusted momentum (price proxy)
    sec = pd.Series({x: sector_of(x) for x in cols})
    sec_mom = sec.map(mom.groupby(sec).mean())
    alpha = mom.rank() + inv_vol.rank() + sec_mom.rank()
    return {"Momentum": mom, "Quality(risk-adj)": quality, "Low-Vol": inv_vol, "Alpha(composite)": alpha}


def main():
    _load()
    methods = ["Random", "Momentum", "Quality(risk-adj)", "Low-Vol", "Alpha(composite)"]
    acc = {m: {"rqs": [], "hit": [], "ic": []} for m in methods}
    rng = np.random.default_rng(0)
    dates = closes.index[::REBAL]
    universe_sizes = []
    for dt in dates:
        i = closes.index.get_loc(dt)
        if i + HOLD >= len(closes):
            continue
        cols = list(rets.loc[:dt].tail(LOOK).dropna(axis=1, how="any").columns)
        if len(cols) < 40:
            continue
        fwd = (closes.iloc[i + HOLD] / closes.iloc[i] - 1).reindex(cols).dropna()
        universe_sizes.append(len(fwd))
        cols = list(fwd.index); pct = fwd.rank(pct=True)            # 1 = best performer
        sc = scores(dt, cols)
        for m in methods:
            if m == "Random":
                picks = list(rng.choice(cols, size=min(TOPN, len(cols)), replace=False))
                ic = np.nan
            else:
                s = sc[m].reindex(cols).dropna()
                picks = list(s.sort_values(ascending=False).head(TOPN).index)
                ic = spearmanr(s, fwd.reindex(s.index)).correlation
            acc[m]["rqs"].append(pct[picks].mean())
            acc[m]["hit"].append((pct[picks] >= 0.75).mean())
            acc[m]["ic"].append(ic)

    N = int(np.median(universe_sizes)) if universe_sizes else 0
    print("=" * 78)
    print(f"  RECOMMENDATION QUALITY SCORECARD  (top-{TOPN}, monthly, 3-month horizon, ~{len(acc['Random']['rqs'])} samples)")
    print("=" * 78)
    print(f"  {'method':<20}{'RQS':>8}{'avg rank':>12}{'Hit% (top-25)':>16}{'IC':>9}{'verdict':>10}")
    for m in methods:
        rqs = np.nanmean(acc[m]["rqs"]); hit = 100 * np.nanmean(acc[m]["hit"])
        ic = np.nanmean(acc[m]["ic"]); rank = (1 - rqs) * N
        verdict = "skill" if rqs > 0.55 else ("weak" if rqs > 0.52 else "none")
        ic_s = f"{ic:+.3f}" if not np.isnan(ic) else "  -- "
        print(f"  {m:<20}{rqs:>8.3f}{rank:>9.0f}/{N}{hit:>14.0f}%{ic_s:>9}{verdict:>10}")
    print("\n  RQS 0.50 = no skill (random) · >0.55 = real recommendation skill · IC>0.05 = useful.")
    print("  Avg rank = where the picks finish out of the universe (lower is better).")
    print("\n  This scorecard is the GATE every new dataset must pass (Track C). A dataset only enters")
    print("  ARJUNA Discover if it lifts RQS/Hit above these price-factor baselines, then survives OOS")
    print("  + forward paper. Quality/Value need POINT-IN-TIME fundamentals (untestable here) -> PIT is")
    print("  dataset #1 precisely because we cannot even score those factors causally yet.")


if __name__ == "__main__":
    main()

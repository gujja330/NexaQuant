# core/usa_explain.py
"""
RC001.6 / .7 / .8 — EXPLAIN the RC001.x findings (analysis, not new framework).

RC001 found: revenue growth +IC, ROE reliably -IC. Before widening coverage we answer WHY, by slicing the
already-built PIT panel. This module READS markets/usa/research/rc001_panel.parquet (the locked research
engine, core/usa_research.py, is NOT modified) and conditions the factor signal:

  RC001.6  by sector  · by regime · by year      -> WHY is ROE negative? where does growth work?
  RC001.7  by market-cap bucket                   -> is the signal a size effect?
  RC001.8  factor interaction (growth x low-debt) -> does combining beat the single factor?

IC here is a POOLED within-date rank-IC (each obs ranked vs the whole market that date, then correlated
inside the bucket) so thin buckets still get a stable read. Honest caveat: 74 names / 21 dates — these are
explanatory leads, not promotions.

Run:  python -m core.usa_explain          # uses cached market caps if present
      python -m core.usa_explain --caps   # (re)fetch market caps via yfinance
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.usa_research import PANEL, FACTORS

CAPS = ROOT / "markets" / "usa" / "processed" / "marketcap.csv"


def load_caps(symbols, refetch=False):
    """Current market cap as an (approximate, snapshot) size classifier. Size BUCKET is stable over ~2y,
    so a snapshot is adequate to ask 'is this a size effect?' — flagged as non-PIT."""
    if CAPS.exists() and not refetch:
        return pd.read_csv(CAPS).set_index("symbol")["market_cap"].to_dict()
    import yfinance as yf
    out = {}
    for s in symbols:
        mc = None
        try:
            mc = yf.Ticker(s).fast_info["market_cap"]            # newer yfinance
        except Exception:
            try:
                mc = yf.Ticker(s).get_info().get("marketCap")    # fallback
            except Exception:
                mc = None
        if mc:
            out[s] = float(mc)
    CAPS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"symbol": list(out), "market_cap": list(out.values())}).to_csv(CAPS, index=False)
    return out


def add_ranks(df):
    """Within-date percentile ranks for each factor and the 63d forward return."""
    df = df.copy()
    df["fwd_dr"] = df.groupby("date")["fwd63"].rank(pct=True)
    for fcol, _ in FACTORS:
        df[fcol + "_dr"] = df.groupby("date")[fcol].rank(pct=True)
    return df


def pooled_ic(df, fcol, sign, minn=40):
    d = df.dropna(subset=[fcol + "_dr", "fwd_dr"])
    if len(d) < minn:
        return None
    return sign * d[fcol + "_dr"].corr(d["fwd_dr"]), len(d)


def slice_table(df, by, factor, sign, minn=40):
    rows = []
    for key, g in df.groupby(by):
        r = pooled_ic(g, factor, sign, minn)
        if r:
            rows.append((str(key), round(r[0], 3), r[1]))
    return sorted(rows, key=lambda x: x[1])


def main():
    if not PANEL.exists():
        print("  no panel — run `python -m core.usa_research` first."); return
    df = add_ranks(pd.read_parquet(PANEL))
    df["year"] = df["date"].str[:4]
    caps = load_caps(sorted(df["symbol"].unique()), refetch="--caps" in sys.argv)
    df["market_cap"] = df["symbol"].map(caps)
    df["cap_bucket"] = pd.qcut(df["market_cap"].rank(method="first"), 4,
                               labels=["Small", "Mid", "Large", "Mega"]) if df["market_cap"].notna().sum() > 8 else np.nan

    print("=" * 70)
    print("  RC001.6/.7/.8 — EXPLAINABILITY (pooled within-date IC, fwd 63d)")
    print("=" * 70)
    print(f"  panel: {len(df)} obs · {df['symbol'].nunique()} names · caps for {df['market_cap'].notna().sum()//df['date'].nunique() if df['date'].nunique() else 0} names\n")

    print("RC001.6  ROE by SECTOR  (WHY is ROE negative? — sign already applied, + = ROE helps)")
    for k, ic, n in slice_table(df, "sector", "f_roe", +1, minn=30):
        flag = "  <- strongly inverse" if ic < -0.08 else ("  <- positive here" if ic > 0.04 else "")
        print(f"    {k:16s} IC {ic:+.3f}  (n={n}){flag}")

    print("\nRC001.6  REVENUE GROWTH by SECTOR  (+ = growth helps)")
    for k, ic, n in slice_table(df, "sector", "f_rev_growth_yoy", +1, minn=30):
        flag = "  <- works here" if ic > 0.08 else ("  <- inverse here" if ic < -0.05 else "")
        print(f"    {k:16s} IC {ic:+.3f}  (n={n}){flag}")

    print("\nRC001.6  by REGIME / YEAR  (composite factors)")
    for fcol, sign, lbl in [("f_roe", +1, "ROE"), ("f_rev_growth_yoy", +1, "Growth")]:
        for by, name in [("bull", "regime bull/bear"), ("year", "year")]:
            parts = [f"{k}={ic:+.3f}" for k, ic, _ in slice_table(df, by, fcol, sign, minn=30)]
            print(f"    {lbl:7s} by {name:16s}: " + "  ".join(parts))

    if df["cap_bucket"].notna().any():
        print("\nRC001.7  by MARKET-CAP BUCKET  (size effect check)")
        for fcol, sign, lbl in [("f_roe", +1, "ROE"), ("f_rev_growth_yoy", +1, "Growth")]:
            parts = [f"{k}={ic:+.3f}(n{n})" for k, ic, n in slice_table(df, "cap_bucket", fcol, sign, minn=30)]
            print(f"    {lbl:7s}: " + "   ".join(parts))
    else:
        print("\nRC001.7  market caps unavailable — run with --caps")

    print("\nRC001.8  INTERACTION  growth x low-debt  (mean fwd percentile, 0.50 = neutral)")
    hi_g = df["f_rev_growth_yoy_dr"] >= 0.5
    lo_d = df["f_debt_to_equity_dr"] <= 0.5            # low leverage
    cells = {
        "high-growth + low-debt ": df[hi_g & lo_d]["fwd_dr"].mean(),
        "high-growth + high-debt": df[hi_g & ~lo_d]["fwd_dr"].mean(),
        "high-growth (any debt) ": df[hi_g]["fwd_dr"].mean(),
        "low-growth (baseline)  ": df[~hi_g]["fwd_dr"].mean(),
    }
    for k, v in cells.items():
        print(f"    {k}: {v:.3f}")
    lift = cells["high-growth + low-debt "] - cells["high-growth (any debt) "]
    print(f"    -> low-debt adds {lift:+.3f} on top of high-growth "
          f"({'interaction helps' if lift > 0.02 else 'no clear interaction'})")
    print("\n  (Explanatory leads on 74 names / 21 dates — investigate, do not promote.)")


if __name__ == "__main__":
    main()

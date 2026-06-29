# core/usa_research.py
"""
USA RESEARCH CYCLE 001.x — deepen, don't flee. RC001 rejected the COMPOSITE; that does NOT mean every
factor failed. This harness extracts everything the SEC dataset can tell us before moving on:

  RC001.0  composite              (already CLOSED: NOT PROMOTED — IC +0.019, lift -0.008)
  RC001.1  individual factors     ROE / margin / growth / leverage each ALONE  (does any single one work?)
  RC001.2  learned blend          LightGBM walk-forward rank vs equal-weight    (does AI beat the mean?)
  RC001.3  sector-conditional     does a factor work inside some sectors only?
  RC001.4  regime-conditional     does it work only in bull / bear (or low/high vol)?
  RC001.5  holding period         63d vs 126d vs 252d  (fundamentals often need longer than price)

Discipline (unchanged): point-in-time (SEC 'filed' dates, no look-ahead), walk-forward, honest about
power. The expensive step (reconstructing PIT fundamentals at every past rebalance) runs ONCE and caches
to markets/usa/research/rc001_panel.parquet; every sub-cycle reads that panel.

Run:  python -m core.usa_research            # build panel (cached) + all sub-cycles
      python -m core.usa_research --rebuild   # force panel rebuild
"""
import sys, glob, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.market_adapter import USAAdapter
from core.usa_fundamentals import normalize_one, RAW

CAD = 21
HORIZONS = [63, 126, 252]
FACTORS = [("f_roe", +1), ("f_net_margin", +1), ("f_rev_growth_yoy", +1), ("f_debt_to_equity", -1)]
PANEL = ROOT / "markets" / "usa" / "research" / "rc001_panel.parquet"


# ---------------------------------------------------------------- panel (expensive, cached)
def build_panel():
    adp = USAAdapter()
    closes, _, _, _, idx, vix, _ = adp.get_market_data()
    covered = [Path(f).stem for f in glob.glob(str(RAW / "*.json")) if Path(f).stem != "cik_map"]
    covered = [c for c in covered if c in closes.columns]
    closes = closes[covered]
    idx = idx.reindex(closes.index).ffill()
    vix = vix.reindex(closes.index).ffill() if vix is not None else None
    vix_med = float(vix.median()) if vix is not None else None
    rows = []
    maxh = max(HORIZONS)
    for i in range(126, len(closes) - 63, CAD):       # need >=63d fwd for the shortest horizon
        dt = str(closes.index[i].date())
        bull = int(idx.iloc[i] > idx.iloc[max(0, i - 200):i].mean())
        highvol = int(vix.iloc[i] > vix_med) if vix is not None else -1
        fwd = {h: (closes.iloc[i + h] / closes.iloc[i] - 1) if i + h < len(closes) else None for h in HORIZONS}
        for s in closes.columns:
            if pd.isna(closes[s].iloc[i]):
                continue
            r = normalize_one(s, today=dt)
            if not r:
                continue
            row = {"date": dt, "symbol": s, "sector": adp.get_sector(s), "bull": bull, "highvol": highvol}
            row.update({k: r.get(k) for k, _ in FACTORS})
            for h in HORIZONS:
                row[f"fwd{h}"] = float(fwd[h][s]) if (fwd[h] is not None and s in fwd[h] and pd.notna(fwd[h][s])) else np.nan
            rows.append(row)
    df = pd.DataFrame(rows)
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PANEL)
    return df


def get_panel(rebuild=False):
    if rebuild or not PANEL.exists():
        print("  building PIT panel (one-time, slow)...")
        return build_panel()
    return pd.read_parquet(PANEL)


# ---------------------------------------------------------------- IC helpers
# Overlap correction: at 21d cadence a 63d forward window overlaps the next ~2 dates (252d: ~11). So
# adjacent-date ICs are autocorrelated and IC-IR is inflated. We measure significance on NON-OVERLAPPING
# dates only (stride = ceil(H/CAD)) so each IC reads an independent forward window.
def stride_for(H):
    return max(1, -(-H // CAD))          # ceil(H/CAD)


def nonoverlap_dates(df, H):
    ds = sorted(df["date"].unique())
    return set(ds[::stride_for(H)])


def ic_series(df, fcol, sign, fwdcol, dates=None):
    """Per-date Spearman IC of signed factor vs forward return (optionally restricted to `dates`)."""
    if dates is not None:
        df = df[df["date"].isin(dates)]
    out = []
    for _, g in df.groupby("date"):
        g = g[[fcol, fwdcol]].dropna()
        if len(g) < 12:
            continue
        out.append(sign * g[fcol].rank().corr(g[fwdcol].rank()))
    return pd.Series([x for x in out if pd.notna(x)], dtype=float)


def summarize(ics):
    if len(ics) < 3:
        return None
    m = float(ics.mean()); ir = m / (ics.std() + 1e-9) * np.sqrt(len(ics))
    return m, ir, len(ics)


def topq_pct(df, fcol, sign, fwdcol, dates=None):
    """Mean forward-return percentile of the top-quartile names by the signed factor (>0.50 = helps)."""
    if dates is not None:
        df = df[df["date"].isin(dates)]
    vals = []
    for _, g in df.groupby("date"):
        g = g[[fcol, fwdcol]].dropna()
        if len(g) < 12:
            continue
        cut = (sign * g[fcol]).quantile(0.75)
        top = g[(sign * g[fcol]) >= cut]
        vals.append(g[fwdcol].rank(pct=True).reindex(top.index).mean())
    return float(np.nanmean(vals)) if vals else np.nan


def verdict(m, ir, tq):
    return "PROMISING" if (m is not None and m > 0.03 and ir > 2.0 and tq > 0.55) else "no"


# ---------------------------------------------------------------- sub-cycles
def rc1_factors(df):
    nd = nonoverlap_dates(df, 63)
    print(f"\nRC001.1  INDIVIDUAL FACTORS  (fwd 63d, non-overlap dates only: {len(nd)})")
    print("  factor                  meanIC   IC-IR   topQ%    n    verdict")
    print("  " + "-" * 62)
    for fcol, sign in FACTORS:
        s = summarize(ic_series(df, fcol, sign, "fwd63", dates=nd))
        tq = topq_pct(df, fcol, sign, "fwd63", dates=nd)
        if s is None:
            print(f"  {fcol:22s}  insufficient"); continue
        m, ir, n = s
        print(f"  {fcol:22s} {m:+.3f}  {ir:+5.2f}  {tq:5.2f}  {n:3d}    {verdict(m, ir, tq)}")


def composite_col(df):
    z = pd.DataFrame(index=df.index)
    for fcol, sign in FACTORS:
        s = df.groupby("date")[fcol].transform(lambda x: (x - x.mean()) / (x.std() + 1e-9))
        z[fcol] = sign * s.clip(-3, 3)
    return z.mean(axis=1)


def _lgbm_ic(df, dates, embargo):
    """Expanding walk-forward LGBM rank-IC. embargo = # of trailing train dates dropped so their forward
    windows do not overlap the test date's window (embargo=0 reproduces the leaky/naive version)."""
    from lightgbm import LGBMRegressor
    feats = [f for f, _ in FACTORS]
    out = []
    for k in range(6, len(dates)):
        cut = k - embargo
        if cut < 3:
            continue
        tr = df[df["date"].isin(dates[:cut])].dropna(subset=feats + ["fwd63"])
        te = df[df["date"] == dates[k]].dropna(subset=feats + ["fwd63"])
        if len(tr) < 60 or len(te) < 12:
            continue
        mdl = LGBMRegressor(n_estimators=120, max_depth=3, learning_rate=0.05,
                            min_child_samples=20, subsample=0.8, verbose=-1)
        mdl.fit(tr[feats], tr["fwd63"])
        p = mdl.predict(te[feats])
        out.append(pd.Series(p, index=te.index).rank().corr(te["fwd63"].rank()))
    return summarize(pd.Series([x for x in out if pd.notna(x)], dtype=float))


def rc2_learned(df):
    print("\nRC001.2  LEARNED BLEND  (LightGBM rank, expanding walk-forward, fwd 63d)")
    try:
        import lightgbm  # noqa
    except Exception:
        print("  skipped (pip install lightgbm)"); return
    dates = sorted(df["date"].unique())
    naive = _lgbm_ic(df, dates, embargo=0)
    purged = _lgbm_ic(df, dates, embargo=stride_for(63))     # drop overlapping-label train dates
    eq = summarize(ic_series(df.assign(_c=composite_col(df)), "_c", 1, "fwd63", dates=nonoverlap_dates(df, 63)))
    if naive:
        print(f"  naive (leaky):    meanIC {naive[0]:+.3f}  IC-IR {naive[1]:+.2f}  n {naive[2]}   <- overlapping windows, do NOT trust")
    if purged:
        print(f"  purged (embargo): meanIC {purged[0]:+.3f}  IC-IR {purged[1]:+.2f}  n {purged[2]}   <- honest")
    if eq:
        print(f"  equal-weight:     meanIC {eq[0]:+.3f}  IC-IR {eq[1]:+.2f}  n {eq[2]}")
    if purged and eq:
        print(f"  -> with leakage removed, learning {'BEATS' if purged[0] > eq[0] + 0.02 else 'does NOT clearly beat'} equal-weight")


def rc3_sector(df):
    nd = nonoverlap_dates(df, 63)
    print("\nRC001.3  SECTOR-CONDITIONAL  (composite, fwd 63d, sectors with >=4 names/date avg)")
    df = df.assign(_c=composite_col(df))
    print("  sector                 meanIC   IC-IR    n")
    print("  " + "-" * 46)
    for sec, g in df.groupby("sector"):
        if g.groupby("date").size().mean() < 4:
            continue
        s = summarize(ic_series(g, "_c", 1, "fwd63", dates=nd))
        if s:
            print(f"  {str(sec):20s} {s[0]:+.3f}  {s[1]:+5.2f}  {s[2]:3d}")


def rc4_regime(df):
    nd = nonoverlap_dates(df, 63)
    print("\nRC001.4  REGIME-CONDITIONAL  (composite, fwd 63d)")
    df = df.assign(_c=composite_col(df))
    for label, mask in [("bull (idx>200dma)", df.bull == 1), ("bear", df.bull == 0),
                        ("low-vol", df.highvol == 0), ("high-vol", df.highvol == 1)]:
        sub = df[mask]
        if sub.empty or (sub.highvol.iloc[0] == -1 and "vol" in label):
            continue
        s = summarize(ic_series(sub, "_c", 1, "fwd63", dates=nd))
        if s:
            print(f"  {label:20s} meanIC {s[0]:+.3f}  IC-IR {s[1]:+5.2f}  n {s[2]}")


def rc5_holding(df):
    print("\nRC001.5  HOLDING PERIOD  (composite)")
    df = df.assign(_c=composite_col(df))
    print("  horizon   meanIC   IC-IR    n  (n = NON-overlapping dates at that horizon)")
    print("  " + "-" * 36)
    for h in HORIZONS:
        s = summarize(ic_series(df, "_c", 1, f"fwd{h}", dates=nonoverlap_dates(df, h)))
        if s:
            print(f"  {h:4d}d   {s[0]:+.3f}  {s[1]:+5.2f}  {s[2]:3d}")
        else:
            print(f"  {h:4d}d   insufficient (too few NON-overlapping {h}d windows to judge)")


def main():
    df = get_panel(rebuild="--rebuild" in sys.argv)
    print("=" * 74)
    print("  USA RESEARCH CYCLE 001.x — SEC fundamentals, deep decomposition")
    print("=" * 74)
    print(f"  panel: {len(df)} rows · {df['symbol'].nunique()} names · {df['date'].nunique()} dates")
    rc1_factors(df)
    rc2_learned(df)
    rc3_sector(df)
    rc4_regime(df)
    rc5_holding(df)
    print("\n  (PIT, walk-forward. Limited USA history + 80-name coverage — read IC-IR, not single ICs.)")


if __name__ == "__main__":
    main()

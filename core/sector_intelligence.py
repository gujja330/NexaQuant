# core/sector_intelligence.py
"""
SECTOR INTELLIGENCE — sectors as intelligent objects, not a single number. Market-agnostic (driven by a
MarketAdapter), so India, USA and any future market share ONE sector model.

Each sector gets a profile from the metrics available today (price-derived) and is designed to be
ENRICHED later (earnings growth, fundamental strength, institutional flow, news) without changing the
shape — each becomes another scored column that plugs into the overall sector score:

    Momentum (3M) · Relative strength vs index · Breadth (% above 200-DMA) · Volatility · Max drawdown
        -> Overall Sector Score (0-100, cross-sector ranked) -> Rotation (BUY / HOLD / SELL)

Stocks inherit their sector's score (sector_score_of), so selection/ranking can use sector context —
exactly the "stock inherits sector" design. Future fundamental/flow columns slot in via the same table.

Run:  python -m core.sector_intelligence india
      python -m core.sector_intelligence usa
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.market_adapter import get_adapter


def sector_table(adapter):
    closes, _, _, _, idx, _, _ = adapter.get_market_data()
    uni = [c for c in closes.columns if c in set(adapter.get_universe())]
    closes = closes[uni]
    rets = closes.pct_change()
    sec_of = {s: adapter.get_sector(s) for s in uni}
    nif3 = 100 * (idx.iloc[-1] / idx.iloc[-64] - 1) if len(idx) > 64 else 0.0
    rows = []
    for sec in sorted(set(sec_of.values())):
        names = [s for s in uni if sec_of[s] == sec]
        if len(names) < 2:
            continue
        sret = rets[names].mean(axis=1)                          # equal-weight sector return
        seq = (1 + sret.fillna(0)).cumprod()
        mom3 = 100 * (seq.iloc[-1] / seq.iloc[-64] - 1) if len(seq) > 64 else np.nan
        above = [closes[s].iloc[-1] > closes[s].tail(200).mean()
                 for s in names if closes[s].notna().sum() > 200]
        breadth = 100 * float(np.mean(above)) if above else np.nan
        vol = float(sret.tail(120).std() * np.sqrt(252) * 100)
        dd = 100 * float(((seq.cummax() - seq) / seq.cummax()).tail(252).max())
        rows.append(dict(Sector=sec, Stocks=len(names), Mom3M=round(mom3, 1),
                         RelStr=round(mom3 - nif3, 1), Breadth=round(breadth), Vol=round(vol), MaxDD=round(dd)))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Overall score: higher momentum/rel-strength/breadth good; higher vol/drawdown bad. Cross-sector rank.
    score = (df["Mom3M"].rank(pct=True) * 0.30 + df["RelStr"].rank(pct=True) * 0.30 +
             df["Breadth"].rank(pct=True) * 0.20 + (1 - df["Vol"].rank(pct=True)) * 0.10 +
             (1 - df["MaxDD"].rank(pct=True)) * 0.10)
    df["Score"] = (score * 100).round().astype(int)
    df["Rotation"] = pd.cut(df["Score"].rank(pct=True), [0, 0.4, 0.7, 1.01],
                            labels=["SELL", "HOLD", "BUY"]).astype(str)
    return df.sort_values("Score", ascending=False).reset_index(drop=True)


def sector_score_of(adapter, table=None):
    """Map symbol -> its sector's Overall Score, so stocks inherit sector context."""
    t = table if table is not None else sector_table(adapter)
    by_sec = dict(zip(t["Sector"], t["Score"])) if not t.empty else {}
    return lambda sym: by_sec.get(adapter.get_sector(sym), 50)


def main():
    market = sys.argv[1] if len(sys.argv) > 1 else "india"
    adp = get_adapter(market)
    t = sector_table(adp)
    print("=" * 84)
    print(f"  SECTOR INTELLIGENCE — {market.upper()}  (price-derived; enrich with fundamentals/flows later)")
    print("=" * 84)
    if t.empty:
        print("  no sectors (need >=2 named stocks per sector)."); return
    print(f"  {'Sector':<16}{'#':>4}{'Mom3M%':>8}{'RelStr%':>9}{'Breadth%':>9}{'Vol%':>6}{'MaxDD%':>7}{'Score':>7}  Rotation")
    for r in t.to_dict("records"):
        print(f"  {r['Sector']:<16}{r['Stocks']:>4}{r['Mom3M']:>8}{r['RelStr']:>+9}{r['Breadth']:>9}"
              f"{r['Vol']:>6}{r['MaxDD']:>7}{r['Score']:>7}  {r['Rotation']}")
    top = t.head(3)["Sector"].tolist()
    print(f"\n  Preferred sectors (rotation BUY): {', '.join(t[t.Rotation=='BUY']['Sector'].tolist()) or '—'}")
    print(f"  Strongest: {', '.join(top)}")


if __name__ == "__main__":
    main()

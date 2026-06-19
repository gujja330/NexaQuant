# india/research/monthly_report_card.py
"""
DETAILED REPORT CARD — every monthly pick, with entry/exit prices and gains (real evidence).
For each month-start from Jan-2025, reconstruct ARJUNA's basket using ONLY data available then
(causal), then for each stock record entry price/date, 1-month & 3-month exit price/date, gain%.

Output: output/arjuna_report_card.xlsx
  - one SHEET PER MONTH (e.g. '2025-01') = every stock: entry, exit, gain%, dates, up/down
  - 'summary' sheet = monthly averages + hit rates
Also a flat output/arjuna_report_card.csv (all stocks, all months).

Run: python india/research/monthly_report_card.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.arjuna_v2 import weights_for
from india.data_nse import NIFTY200

OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)
START, TOPN, NAME_CAP, LOOKBACK = "2025-01-01", 30, 0.05, 120


def main():
    closes = load_panels()[0]
    cols = [c for c in closes.columns if c in set(NIFTY200)]
    closes = closes[cols]; rets = closes.pct_change(); didx = closes.index
    mask = didx >= pd.Timestamp(START)
    mstarts = pd.Series(didx[mask], index=didx[mask]).groupby(
        [didx[mask].year, didx[mask].month]).first().values

    per_month, all_rows, summary = {}, [], []
    for d in mstarts:
        d = pd.Timestamp(d); i = didx.get_loc(d)
        hist = rets.loc[:d].tail(LOOKBACK).dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        w = weights_for("hrp", hist).clip(upper=NAME_CAP)
        w = (w / w.sum()).sort_values(ascending=False).head(TOPN)
        d1 = didx[i + 21] if i + 21 < len(didx) else None
        d3 = didx[i + 63] if i + 63 < len(didx) else None
        recs = []
        for s, wt in w.items():
            entry = float(closes.loc[d, s])
            p1 = float(closes.loc[d1, s]) if d1 is not None else np.nan
            p3 = float(closes.loc[d3, s]) if d3 is not None else np.nan
            g1 = (p1 / entry - 1) * 100 if np.isfinite(p1) else np.nan
            g3 = (p3 / entry - 1) * 100 if np.isfinite(p3) else np.nan
            recs.append({
                "stock": s, "weight_%": round(100 * wt, 1),
                "buy_date": d.date(), "buy_price": round(entry, 1),
                "exit_1m_date": d1.date() if d1 is not None else None,
                "exit_1m_price": round(p1, 1) if np.isfinite(p1) else None,
                "gain_1m_%": round(g1, 1) if np.isfinite(g1) else None,
                "result_1m": ("UP" if g1 > 0 else "DOWN") if np.isfinite(g1) else "open",
                "exit_3m_date": d3.date() if d3 is not None else None,
                "exit_3m_price": round(p3, 1) if np.isfinite(p3) else None,
                "gain_3m_%": round(g3, 1) if np.isfinite(g3) else None,
                "result_3m": ("UP" if g3 > 0 else "DOWN") if np.isfinite(g3) else "open"})
        mdf = pd.DataFrame(recs)
        per_month[d.strftime("%Y-%m")] = mdf
        for r in recs:
            all_rows.append({"month": d.strftime("%Y-%m"), **r})
        g1s = mdf["gain_1m_%"].dropna(); g3s = mdf["gain_3m_%"].dropna()
        summary.append({"month": d.strftime("%Y-%m"), "picks": len(mdf),
                        "avg_gain_1m_%": round(g1s.mean(), 1) if len(g1s) else None,
                        "winners_1m": f"{(mdf['result_1m']=='UP').sum()}/{mdf['result_1m'].isin(['UP','DOWN']).sum()}",
                        "avg_gain_3m_%": round(g3s.mean(), 1) if len(g3s) else None,
                        "winners_3m": f"{(mdf['result_3m']=='UP').sum()}/{mdf['result_3m'].isin(['UP','DOWN']).sum()}"})

    flat = pd.DataFrame(all_rows); flat.to_csv(OUT / "arjuna_report_card.csv", index=False)
    sm = pd.DataFrame(summary)
    with pd.ExcelWriter(OUT / "arjuna_report_card.xlsx") as xl:
        sm.to_excel(xl, sheet_name="summary", index=False)
        for month, mdf in per_month.items():
            mdf.to_excel(xl, sheet_name=month, index=False)

    print("=" * 70)
    print("  DETAILED REPORT CARD saved -> output/arjuna_report_card.xlsx")
    print(f"  ({len(per_month)} monthly sheets + summary; {len(flat)} stock-picks total)")
    print("=" * 70)
    print("  SAMPLE — 2025-03 picks (first 10), entry -> 1-month exit:\n")
    s = per_month.get("2025-03")
    if s is not None:
        print(s[["stock", "buy_price", "exit_1m_price", "gain_1m_%", "result_1m", "gain_3m_%", "result_3m"]].head(10).to_string(index=False))
    print("\n  Open the xlsx: one tab per month, every stock with buy/exit price + gain%.")


if __name__ == "__main__":
    main()

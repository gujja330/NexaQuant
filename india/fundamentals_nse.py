# india/fundamentals_nse.py
"""
FUNDAMENTALS + EARNINGS calendar for NSE stocks, from a FREE source (yfinance).

Two layers:
  1. QUALITY SNAPSHOT (current): ROE, debt/equity, profit margin, earnings growth, PE, PB ->
     a cross-sectional QUALITY z-score. yfinance .info is a CURRENT snapshot (not point-in-time
     history), so this is a LIVE SCREEN/TILT — it improves which names we hold *now*, but it
     cannot be backtested historically without paid point-in-time data (be honest about that).
  2. EARNINGS CALENDAR: next results date per stock -> so the bot can (a) ride POST-earnings
     drift (PEAD, a documented anomaly) and (b) size DOWN into a result it has no edge on.
     We do NOT try to predict the surprise before it prints (not a real, legal edge).

Output: data/raw/india/fundamentals.parquet (quality score + raw metrics + next_earnings).

Run:  python india/fundamentals_nse.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.data_nse import UNIVERSE
OUT = ROOT / "data" / "raw" / "india" / "fundamentals.parquet"

# higher is better (+1) or lower is better (-1) for the quality score
METRICS = {"returnOnEquity": +1, "profitMargins": +1, "earningsGrowth": +1,
           "debtToEquity": -1, "trailingPE": -1, "priceToBook": -1}


def pull():
    import yfinance as yf
    rows = {}
    for sym in UNIVERSE:
        if sym.startswith("^"):
            continue
        try:
            t = yf.Ticker(sym)
            i = t.info
            rec = {m: i.get(m) for m in METRICS}
            # next earnings date (for the calendar / PEAD + risk-aware sizing)
            nxt = None
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed:
                        nxt = str(ed[0] if isinstance(ed, (list, tuple)) else ed)
            except Exception:
                pass
            rec["next_earnings"] = nxt
            rows[sym.replace(".NS", "")] = rec
            print(f"  {sym:<14} ROE={rec.get('returnOnEquity')}  D/E={rec.get('debtToEquity')}  "
                  f"PE={rec.get('trailingPE')}  next_earn={nxt}")
        except Exception as e:
            print(f"  ! {sym}: {e}")
    return pd.DataFrame(rows).T


def quality_score(df):
    """Cross-sectional z-score blend of the quality metrics (higher = better fundamentals)."""
    z = pd.DataFrame(index=df.index)
    for m, sign in METRICS.items():
        col = pd.to_numeric(df[m], errors="coerce")
        zc = (col - col.mean()) / (col.std() + 1e-9)
        z[m] = sign * zc
    return z.mean(axis=1)


def main():
    print("=== NSE fundamentals + earnings calendar (yfinance, free, CURRENT snapshot) ===")
    df = pull()
    if df.empty:
        print("  ! no data"); return
    df["quality_score"] = quality_score(df)
    df = df.sort_values("quality_score", ascending=False)
    df.to_parquet(OUT)
    print(f"\n  saved {OUT}")
    print("\n  Top quality names (current snapshot):")
    print(df[["quality_score", "returnOnEquity", "debtToEquity", "trailingPE", "next_earnings"]].head(8).to_string())
    print("\n  NOTE: snapshot only -> use as a LIVE screen/tilt on top of momentum+low-vol, NOT a")
    print("        historical backtest. Earnings dates enable PEAD-drift + risk-aware sizing.")


if __name__ == "__main__":
    main()

# data/pull_yfinance.py
"""
Deep DAILY history via yfinance (free, no key) — for multi-regime / multi-year validation.

yfinance only serves long history at DAILY resolution (intraday is capped to ~60 days), so
this is for the WALK-FORWARD / regime robustness tests, not intraday execution. Gold futures
(GC=F) reach back to 2000 — covering 2008, 2011 top, 2013 bear, 2015 range, 2020, 2022, etc.

Saves data/raw/<SYMBOL>_D1.parquet (repo schema). Uses a 'd' suffix symbol (e.g. XAUUSDd)
so it does NOT overwrite the broker intraday data (XAUUSDm H1/H4/D1).

Run: python data/pull_yfinance.py
     python data/pull_yfinance.py "GC=F:XAUUSDd" "EURUSD=X:EURUSDd" "^GSPC:SPXd"
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
DEFAULT = ["GC=F:XAUUSDd", "BTC-USD:BTCUSDd", "EURUSD=X:EURUSDd", "^GSPC:SPXd", "CL=F:WTId"]


def pull(ticker, symbol):
    import yfinance as yf
    d = yf.download(ticker, period="max", interval="1d", progress=False, auto_adjust=True)
    if d.empty:
        print(f"  ! {ticker}: no data"); return
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d.rename(columns=str.lower)
    out = pd.DataFrame(index=pd.DatetimeIndex(d.index, name="time"))
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(d[c], errors="coerce")
    vol = pd.to_numeric(d.get("volume", 0), errors="coerce").fillna(0)
    out["tick_volume"] = vol; out["spread"] = 0.0; out["real_volume"] = vol
    out = out.dropna(subset=["close"])
    path = RAW / f"{symbol}_D1.parquet"
    out.to_parquet(path)
    print(f"  saved {path}  ({len(out)} days, {out.index[0].date()} -> {out.index[-1].date()})")


def main():
    pairs = sys.argv[1:] or DEFAULT
    print("=== yfinance deep daily history ===")
    for pr in pairs:
        t, s = pr.split(":")
        try:
            pull(t, s)
        except Exception as e:
            print(f"  ! {pr}: {type(e).__name__} {str(e)[:90]}")


if __name__ == "__main__":
    main()

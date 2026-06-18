# india/data_nse.py
"""
Pull FREE Indian equity data (NSE) for validation — daily OHLC via yfinance, no account.

Universe = liquid Nifty large-caps + the Nifty 50 and Bank Nifty indices. Saved to
data/raw/india/<SYM>_D1.parquet in the same OHLC format the strategy expects, so the existing
trend/breakout logic runs on them unchanged. This is the BACKTEST data source; live intraday
data later comes from the broker API (Angel One / Upstox).

Run:  python india/data_nse.py            # default universe, ~6y daily
      python india/data_nse.py --years 8
"""
import argparse
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "india"
OUT.mkdir(parents=True, exist_ok=True)

# liquid, algo-friendly Nifty large-caps + indices (yfinance symbols). Edit freely.
UNIVERSE = [
    "^NSEI", "^NSEBANK",                                   # Nifty 50, Bank Nifty (indices)
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "SBIN.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS", "HINDUNILVR.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS", "WIPRO.NS",
    "TATAMOTORS.NS", "TATASTEEL.NS", "ADANIENT.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS",
    # ---- expansion: more liquid Nifty-100/200 names (reduce concentration/survivorship bias) ----
    "MM.NS", "HCLTECH.NS", "TECHM.NS", "ULTRACEMCO.NS", "NESTLEIND.NS", "BAJAJFINSV.NS",
    "HDFCLIFE.NS", "GRASIM.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS", "BPCL.NS",
    "DRREDDY.NS", "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BRITANNIA.NS", "DABUR.NS",
    "DLF.NS", "ADANIPORTS.NS", "GAIL.NS", "TATACONSUM.NS", "BANKBARODA.NS", "PNB.NS",
    "VEDL.NS", "JINDALSTEL.NS", "SAIL.NS",
]


def fetch(sym, years):
    import yfinance as yf
    df = yf.download(sym, period=f"{years}y", interval="1d", auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    df = df.rename(columns=str.lower)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]            # flatten single-ticker multiindex
    out = pd.DataFrame(index=df.index)
    for c in ("open", "high", "low", "close"):
        if c not in df.columns:
            return None
        out[c] = pd.to_numeric(df[c], errors="coerce")
    out["tick_volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    out["spread"] = 0.0
    out.index.name = "time"
    return out.dropna(subset=["close"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--symbols", nargs="+", default=UNIVERSE)
    a = ap.parse_args()
    print(f"=== Indian equity pull (yfinance, {a.years}y daily) -> {OUT} ===")
    ok = 0
    for sym in a.symbols:
        df = fetch(sym, a.years)
        if df is None or len(df) < 200:
            print(f"  ! {sym}: no/low data"); continue
        fn = sym.replace("^", "").replace(".NS", "") + "_D1.parquet"
        df.to_parquet(OUT / fn)
        ok += 1
        print(f"  {sym:<14} {len(df):>5} bars  {df.index[0].date()} -> {df.index[-1].date()}  -> {fn}")
    print(f"\nSaved {ok}/{len(a.symbols)} symbols. Next: python india/validate_india.py")


if __name__ == "__main__":
    main()

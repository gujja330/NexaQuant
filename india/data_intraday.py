# india/data_intraday.py
"""
Pull FREE intraday (HOURLY) NSE data for the intraday engine + macro series for the guard.

  * Hourly bars (~2 years) for the stock universe + Nifty  -> data/raw/india/intraday/<SYM>_H1.parquet
    (yfinance gives ~730d of 1h bars free; 5m/15m only ~60d, so hourly is the backtestable choice)
  * India VIX (^INDIAVIX) + S&P 500 (^GSPC) daily          -> data/raw/india/  (volatility + global cue)

Run: python india/data_intraday.py
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.data_nse import UNIVERSE
RAW = ROOT / "data" / "raw" / "india"
INTRA = RAW / "intraday"; INTRA.mkdir(parents=True, exist_ok=True)


def _ohlc(df):
    df = df.rename(columns=str.lower)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    out = pd.DataFrame(index=df.index)
    for c in ("open", "high", "low", "close"):
        if c not in df.columns:
            return None
        out[c] = pd.to_numeric(df[c], errors="coerce")
    out["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    out.index.name = "time"
    return out.dropna(subset=["close"])


def main():
    import yfinance as yf
    stocks = [s for s in UNIVERSE if s != "^NSEBANK"]   # stocks + Nifty (for VWAP/RS benchmark)
    print(f"=== Hourly pull (~2y) for {len(stocks)} symbols -> {INTRA} ===")
    ok = 0
    for sym in stocks:
        try:
            df = yf.download(sym, period="730d", interval="1h", auto_adjust=True, progress=False)
            o = _ohlc(df)
            if o is None or len(o) < 500:
                print(f"  ! {sym}: low/no hourly"); continue
            fn = sym.replace("^", "").replace(".NS", "") + "_H1.parquet"
            o.to_parquet(INTRA / fn); ok += 1
            print(f"  {sym:<14}{len(o):>6} 1h bars  {o.index[0].date()} -> {o.index[-1].date()}")
        except Exception as e:
            print(f"  ! {sym}: {e}")
    print(f"  hourly: {ok}/{len(stocks)} saved")

    # macro series (daily): India VIX + S&P 500
    print("\n=== Macro (daily): India VIX + S&P 500 ===")
    for sym, name in [("^INDIAVIX", "INDIAVIX"), ("^GSPC", "SP500")]:
        try:
            df = yf.download(sym, period="6y", interval="1d", auto_adjust=True, progress=False)
            o = _ohlc(df)
            if o is not None:
                o.to_parquet(RAW / f"{name}_D1.parquet")
                print(f"  {sym:<12}{len(o):>6} bars -> {name}_D1.parquet")
        except Exception as e:
            print(f"  ! {sym}: {e}")


if __name__ == "__main__":
    main()

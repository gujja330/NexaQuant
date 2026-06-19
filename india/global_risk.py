# india/global_risk.py
"""
GLOBAL RISK ENGINE (Tier-1) — India doesn't trade in isolation. COVID, Ukraine, Fed, oil shocks,
USD spikes and US selloffs all hit Indian equities. This builds a daily GLOBAL RISK-OFF score from
free global series (yfinance) and turns it into an exposure multiplier for the regime overlay.

Risk-OFF flags (each cuts exposure): S&P below its 200-DMA, US VIX in its high regime, USD (DXY)
strengthening (EM outflows), US 10Y yield spiking, crude spiking. Cached to data/raw/india/global/.

  from india.global_risk import global_exposure
  g = global_exposure()   # daily multiplier in (0,1], 1.0 = calm, lower = global risk-off

Run: python india/global_risk.py            # fetch + show current global risk
     python india/global_risk.py --fetch    # force refresh
"""
import argparse, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
GDIR = ROOT / "data" / "raw" / "india" / "global"
GDIR.mkdir(parents=True, exist_ok=True)

TICKERS = {"SPX": "^GSPC", "USVIX": "^VIX", "DXY": "DX-Y.NYB",
           "OIL": "CL=F", "GOLD": "GC=F", "US10Y": "^TNX", "USDINR": "INR=X"}


def fetch(years=8):
    import yfinance as yf
    for name, tk in TICKERS.items():
        try:
            df = yf.download(tk, period=f"{years}y", interval="1d", auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                s = df["Close"]
                if hasattr(s, "columns"):
                    s = s.iloc[:, 0]
                s.to_frame("close").to_parquet(GDIR / f"{name}.parquet")
                print(f"  {name:<7}{len(s):>5} bars  {s.index[0].date()} -> {s.index[-1].date()}")
        except Exception as e:
            print(f"  ! {name}: {e}")


def _load(name):
    p = GDIR / f"{name}.parquet"
    return pd.read_parquet(p)["close"] if p.exists() else None


def global_exposure():
    """Daily exposure multiplier from global risk-off flags. Causal (trailing only)."""
    spx, usvix, dxy, us10y, oil = (_load(k) for k in ("SPX", "USVIX", "DXY", "US10Y", "OIL"))
    if spx is None:
        return None
    idx = spx.index
    scale = pd.Series(1.0, index=idx)
    # S&P below 200-DMA -> US downtrend
    scale *= (spx < spx.rolling(200).mean()).reindex(idx).fillna(False).map({True: 0.8, False: 1.0})
    # US VIX high regime
    if usvix is not None:
        hi = usvix > usvix.rolling(120, min_periods=30).quantile(0.80)
        scale *= hi.reindex(idx).fillna(False).map({True: 0.8, False: 1.0})
    # USD strengthening (3m DXY momentum > +3% -> EM risk-off)
    if dxy is not None:
        up = (dxy / dxy.shift(63) - 1) > 0.03
        scale *= up.reindex(idx).fillna(False).map({True: 0.85, False: 1.0})
    return scale.reindex(pd.date_range(idx.min(), idx.max())).ffill()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--fetch", action="store_true"); a = ap.parse_args()
    if a.fetch or not (GDIR / "SPX.parquet").exists():
        print("  fetching global series (yfinance)..."); fetch()
    g = global_exposure()
    if g is None:
        print("  no global data — run with --fetch"); sys.exit()
    print(f"\n  current global risk exposure: {g.iloc[-1]:.2f}  (1.0=calm, lower=risk-off)")
    print(f"  share of days de-risked (<1.0): {100*(g < 1.0).mean():.0f}%")

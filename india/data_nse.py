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

# NIFTY 100 universe (liquid large+midcaps) + indices (yfinance symbols). Breadth fixes the
# concentration that doubled drawdown; ~100 names give the AI ranker something to rank ACROSS.
INDICES = ["^NSEI", "^NSEBANK"]                            # Nifty 50, Bank Nifty
UNIVERSE = INDICES + [
    # ---- Nifty 50 core ----
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "SBIN.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS", "HINDUNILVR.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS", "WIPRO.NS",
    "TATAMOTORS.NS", "TATASTEEL.NS", "ADANIENT.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS",
    "MM.NS", "HCLTECH.NS", "TECHM.NS", "ULTRACEMCO.NS", "NESTLEIND.NS", "BAJAJFINSV.NS",
    "HDFCLIFE.NS", "GRASIM.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS", "BPCL.NS",
    "DRREDDY.NS", "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BRITANNIA.NS", "ADANIPORTS.NS",
    "TATACONSUM.NS", "APOLLOHOSP.NS", "BAJAJ-AUTO.NS", "INDUSINDBK.NS", "SBILIFE.NS",
    "SHRIRAMFIN.NS", "TRENT.NS", "JIOFIN.NS",
    # ---- Nifty Next 50 / liquid large-caps (to ~100) ----
    "DABUR.NS", "DLF.NS", "GAIL.NS", "BANKBARODA.NS", "PNB.NS", "VEDL.NS", "JINDALSTEL.NS",
    "SAIL.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "AMBUJACEM.NS", "ABB.NS", "CANBK.NS",
    "BEL.NS", "BOSCHLTD.NS", "CHOLAFIN.NS", "COLPAL.NS", "DMART.NS", "GODREJCP.NS",
    "HAVELLS.NS", "HAL.NS", "ICICIGI.NS", "ICICIPRULI.NS", "IOC.NS", "INDIGO.NS",
    "NAUKRI.NS", "LICI.NS", "LTIM.NS", "MOTHERSON.NS", "MARICO.NS", "MUTHOOTFIN.NS",
    "PIDILITIND.NS", "PFC.NS", "RECLTD.NS", "SIEMENS.NS", "SRF.NS", "SHREECEM.NS",
    "TATAPOWER.NS", "TORNTPHARM.NS", "TVSMOTOR.NS", "UNITDSPR.NS", "VBL.NS", "ZYDUSLIFE.NS",
    "PAGEIND.NS", "BIOCON.NS", "LUPIN.NS", "MPHASIS.NS", "COFORGE.NS", "POLYCAB.NS",
    "INDHOTEL.NS", "MAXHEALTH.NS", "PETRONET.NS",
    # ---- Nifty 101-200 (liquid midcaps -> broaden to ~Nifty 200) ----
    "PERSISTENT.NS", "OFSS.NS", "LTTS.NS", "KPITTECH.NS", "TATAELXSI.NS", "SONACOMS.NS",
    "ESCORTS.NS", "ASHOKLEY.NS", "BHARATFORG.NS", "MRF.NS", "BALKRISIND.NS", "APOLLOTYRE.NS",
    "CUMMINSIND.NS", "EXIDEIND.NS", "TIINDIA.NS", "UNOMINDA.NS", "ALKEM.NS", "AUROPHARMA.NS",
    "GLENMARK.NS", "IPCALAB.NS", "LAURUSLABS.NS", "AJANTPHARM.NS", "GLAND.NS", "NATCOPHARM.NS",
    "FORTIS.NS", "LALPATHLAB.NS", "SYNGENE.NS", "ABBOTINDIA.NS", "METROPOLIS.NS", "BANDHANBNK.NS",
    "FEDERALBNK.NS", "IDFCFIRSTB.NS", "AUBANK.NS", "INDIANB.NS", "UNIONBANK.NS", "YESBANK.NS",
    "RBLBANK.NS", "LICHSGFIN.NS", "SBICARD.NS", "BAJAJHLDNG.NS", "MFSL.NS", "CHOLAHLDNG.NS",
    "SUNDARMFIN.NS", "MANAPPURAM.NS", "ABCAPITAL.NS", "PEL.NS", "CDSL.NS", "BSE.NS", "MCX.NS",
    "ANGELONE.NS", "IEX.NS", "KFINTECH.NS", "CAMS.NS", "PAYTM.NS", "NYKAA.NS", "DELHIVERY.NS",
    "POLICYBZR.NS", "IRCTC.NS", "IRFC.NS", "RVNL.NS", "IRB.NS", "NHPC.NS", "SJVN.NS",
    "NLCINDIA.NS", "CONCOR.NS", "NMDC.NS", "HINDZINC.NS", "NATIONALUM.NS", "OIL.NS",
    "MAZDOCK.NS", "TATACHEM.NS", "DEEPAKNTR.NS", "AARTIIND.NS", "NAVINFLUOR.NS", "GNFC.NS",
    "COROMANDEL.NS", "UPL.NS", "PIIND.NS", "ATUL.NS", "VINATIORGA.NS", "CHAMBLFERT.NS",
    "BALRAMCHIN.NS", "DALBHARAT.NS", "JKCEMENT.NS", "RAMCOCEM.NS", "ACC.NS", "APLAPOLLO.NS",
    "JINDALSAW.NS", "RATNAMANI.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS",
    "PRESTIGE.NS", "LODHA.NS", "TORNTPOWER.NS", "JSWENERGY.NS", "IGL.NS", "MGL.NS",
    "GUJGASLTD.NS", "CESC.NS", "UBL.NS", "RADICO.NS", "PATANJALI.NS", "GODREJIND.NS",
    "EMAMILTD.NS", "JUBLFOOD.NS", "BATAINDIA.NS", "RELAXO.NS", "VOLTAS.NS", "BLUESTARCO.NS",
    "DIXON.NS", "AMBER.NS", "CROMPTON.NS", "KAJARIACER.NS", "SUPREMEIND.NS", "ASTRAL.NS",
    "THERMAX.NS", "AIAENG.NS", "KEI.NS", "CGPOWER.NS", "KALYANKJIL.NS", "INDUSTOWER.NS",
    "TATACOMM.NS", "PVRINOX.NS", "SUNTV.NS", "GMRAIRPORT.NS",
]

# clean symbols (no .NS / index ^) — first 100 = Nifty-100, all = Nifty-200. Single source of truth.
STOCKS = [s.replace(".NS", "").replace("^", "") for s in UNIVERSE if not s.startswith("^")]
NIFTY100 = STOCKS[:100]
NIFTY200 = STOCKS


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

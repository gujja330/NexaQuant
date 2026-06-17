# data/fundamentals.py
"""
Fundamental / macro feature layer for gold + BTC -- FREE data sources only.

For gold and BTC, "fundamentals" = MACRO & FLOW, not company earnings. The big drivers:
  Gold : US real yields (inverse), USD/DXY (inverse), Fed policy, COT positioning
  BTC  : USD liquidity, risk sentiment (Nasdaq), funding/open interest, ETF flows

This module pulls those series, builds a leakage-safe daily MACRO-BIAS feature set,
and saves data/raw/FUNDAMENTALS.parquet. The AI meta-labeler (strategy/meta_label.py)
auto-loads it and fills its FUNDAMENTAL_COLS -> predictions get stronger, no code change.

FREE sources (no paid keys):
  * yfinance        : ^TNX (10y yield), DX-Y.NYB (DXY), ^GSPC, ^IXIC, GC=F, BTC-USD   (no key)
  * FRED (optional) : DFII10 real yield, set FRED_API_KEY for true real yields         (free key)
  * CFTC COT        : Socrata public dataset, no key (managed-money net positioning)

LEAKAGE CONTROL: economic series are revised and released with a lag. We stamp each
value to the day AFTER its date and only ever join it backward (merge_asof), so a
backtest bar only sees macro data that was already public.

Run (needs network):  python data/fundamentals.py
"""
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "FUNDAMENTALS.parquet"

# columns consumed by strategy/meta_label.py (must match FUNDAMENTAL_COLS there)
COLS = ["f_real_yield_trend", "f_dxy_trend", "f_cot_net_long", "f_event_within_24h"]


def _trend(s, n=20):
    """Sign-scaled slope: +1 rising, -1 falling, over n days (z-scored slope)."""
    chg = s - s.shift(n)
    return np.tanh(chg / (s.rolling(n).std() + 1e-9))


def pull_yfinance():
    import yfinance as yf
    data = yf.download(["^TNX", "DX-Y.NYB"], period="3y", interval="1d", progress=False)["Close"]
    data = data.rename(columns={"^TNX": "yield10", "DX-Y.NYB": "dxy"}).dropna(how="all")
    out = pd.DataFrame(index=data.index)
    # gold is INVERSE to yields and DXY -> bullish bias when both falling
    out["f_real_yield_trend"] = -_trend(data["yield10"])     # +ve = yields falling = gold bullish
    out["f_dxy_trend"] = -_trend(data["dxy"])                # +ve = USD falling = gold bullish
    return out


def pull_fred_real_yield():
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return None
    import requests
    url = ("https://api.stlouisfed.org/fred/series/observations"
           f"?series_id=DFII10&api_key={key}&file_type=json")
    obs = requests.get(url, timeout=30).json().get("observations", [])
    s = pd.Series({pd.to_datetime(o["date"]): float(o["value"])
                   for o in obs if o["value"] not in (".", "")}).sort_index()
    return (-_trend(s)).rename("f_real_yield_trend").to_frame()


def pull_cot_gold():
    """CFTC Commitment of Traders -- managed-money net long in gold (Socrata, no key)."""
    try:
        import requests
        url = ("https://publicreporting.cftc.gov/resource/6dca-aqww.json"
               "?$where=contract_market_name like 'GOLD%25'&$order=report_date_as_yyyy_mm_dd DESC&$limit=200")
        rows = requests.get(url, timeout=30).json()
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"])
        net = (df["m_money_positions_long_all"].astype(float)
               - df["m_money_positions_short_all"].astype(float))
        s = pd.Series(net.values, index=df["date"]).sort_index()
        return (np.tanh((s - s.rolling(52).mean()) / (s.rolling(52).std() + 1e-9))
                ).rename("f_cot_net_long").to_frame()
    except Exception as e:
        print(f"  ! COT pull skipped: {e}")
        return None


def build():
    frames = []
    try:
        frames.append(pull_yfinance())
    except Exception as e:
        sys.exit(f"yfinance pull failed (need network / `pip install yfinance`): {e}")
    fred = pull_fred_real_yield()
    if fred is not None:
        frames[0]["f_real_yield_trend"] = fred["f_real_yield_trend"].reindex(frames[0].index).ffill()
        print("  used FRED DFII10 real yields")
    cot = pull_cot_gold()
    macro = frames[0]
    if cot is not None:
        macro = macro.join(cot.reindex(macro.index).ffill(), how="left")
    else:
        macro["f_cot_net_long"] = np.nan
    macro["f_event_within_24h"] = np.nan   # filled by an economic-calendar puller (next module)
    # LEAKAGE GUARD: shift to next day = only available AFTER the day closes
    macro = macro[COLS].shift(1).dropna(how="all")
    macro.index.name = "time"
    macro.to_parquet(OUT)
    print(f"  saved {OUT}  ({len(macro)} days, {macro.index.min().date()} -> {macro.index.max().date()})")


def load_fundamentals(index):
    """Leakage-safe as-of join of FUNDAMENTALS.parquet (+ SENTIMENT.parquet) onto an
    intraday index. Returns a DataFrame aligned to `index` (empty if no files)."""
    frames = [pd.read_parquet(p).sort_index()
              for p in (OUT, RAW / "SENTIMENT.parquet") if p.exists()]
    if not frames:
        return pd.DataFrame(index=index)
    f = pd.concat(frames, axis=1)
    f = f.loc[:, ~f.columns.duplicated()].sort_index()
    left = pd.DataFrame(index=index).reset_index().rename(columns={index.name or "index": "time"})
    if left.columns[0] != "time":
        left = left.rename(columns={left.columns[0]: "time"})
    merged = pd.merge_asof(left.sort_values("time"), f.reset_index().sort_values("time"),
                           on="time", direction="backward")
    return merged.set_index("time")[f.columns]


if __name__ == "__main__":
    print("=== building macro fundamentals ===")
    build()

# data/pull_stooq.py
"""
NO-API-KEY historical OHLCV + macro from Stooq (stooq.com) — a trusted free source.

Stooq serves plain-CSV daily history for gold, FX, indices, commodities and macro
proxies with NO key and NO login:
    https://stooq.com/q/d/l/?s=<symbol>&i=d   ->  Date,Open,High,Low,Close,Volume

This fixes the "one regime" problem for GOLD specifically: Stooq's xauusd history runs
back ~2 decades (2008 crash, 2011 top, 2013-15 bear, 2018 range, 2020+ bull) — many
regimes, free, no key.

Saves OHLCV to data/raw/<SYMBOL>_D1.parquet (repo convention -> probes auto-include),
and macro series to data/raw/FUNDAMENTALS.parquet columns where applicable.

Run (needs network):
  python data/pull_stooq.py --ohlcv xauusd:XAUUSDm btcusd:BTCUSDm eurusd:EURUSDm
  python data/pull_stooq.py --macro            # build no-key macro fundamentals
"""
import argparse
import io
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://stooq.com/q/d/l/?s={sym}&i=d"
HEADERS = {"User-Agent": "Mozilla/5.0"}   # stooq blocks empty UA

# macro proxies on Stooq (all no-key). Gold is INVERSE to USD & yields.
MACRO = {"dxy": "^dxy", "ust10y": "^tnx", "vix": "^vix", "spx": "^spx", "wti": "cl.f"}


def fetch(sym):
    r = requests.get(BASE.format(sym=sym), headers=HEADERS, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if "Date" not in df.columns or df.empty:
        raise ValueError(f"no data for {sym} (got: {df.columns.tolist()})")
    df["time"] = pd.to_datetime(df["Date"])
    return df.set_index("time").sort_index()


def pull_ohlcv(stooq_sym, repo_sym):
    df = fetch(stooq_sym)
    out = pd.DataFrame({
        "open": df["Open"].astype(float), "high": df["High"].astype(float),
        "low": df["Low"].astype(float), "close": df["Close"].astype(float),
        "tick_volume": df.get("Volume", pd.Series(0, index=df.index)).fillna(0).astype(float),
        "spread": 0.0, "real_volume": df.get("Volume", pd.Series(0, index=df.index)).fillna(0).astype(float)},
        index=df.index)
    path = RAW / f"{repo_sym}_D1.parquet"
    out.to_parquet(path)
    print(f"  saved {path}  ({len(out)} days, {out.index[0].date()} -> {out.index[-1].date()})")


def trend(s, n=20):
    return np.tanh((s - s.shift(n)) / (s.rolling(n).std() + 1e-9))


def build_macro():
    """No-key macro fundamentals for gold: bias from yields & USD (both inverse)."""
    series = {}
    for name, sym in MACRO.items():
        try:
            series[name] = fetch(sym)["Close"].astype(float)
            print(f"  pulled {name} ({sym})")
        except Exception as e:
            print(f"  ! {name} ({sym}): {e}")
    if not series:
        sys.exit("no macro series fetched (network?)")
    idx = sorted(set().union(*[s.index for s in series.values()]))
    m = pd.DataFrame(index=pd.DatetimeIndex(idx))
    if "ust10y" in series:
        m["f_real_yield_trend"] = -trend(series["ust10y"].reindex(m.index).ffill())   # yields down -> gold up
    if "dxy" in series:
        m["f_dxy_trend"] = -trend(series["dxy"].reindex(m.index).ffill())             # USD down -> gold up
    if "vix" in series:
        m["f_risk_off"] = trend(series["vix"].reindex(m.index).ffill())               # fear up -> gold bid
    m["f_cot_net_long"] = np.nan       # fill via data/fundamentals.py (CFTC, also no key)
    m["f_event_within_24h"] = np.nan
    m = m.shift(1).dropna(how="all")   # leakage guard: available next day
    m.index.name = "time"
    out = RAW / "FUNDAMENTALS.parquet"
    m.to_parquet(out)
    print(f"  saved {out}  ({len(m)} days, cols={list(m.columns)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ohlcv", nargs="*", default=[], help="pairs like xauusd:XAUUSDm btcusd:BTCUSDm")
    ap.add_argument("--macro", action="store_true", help="build no-key macro fundamentals")
    args = ap.parse_args()
    if not args.ohlcv and not args.macro:
        args.ohlcv = ["xauusd:XAUUSDm", "btcusd:BTCUSDm"]   # sensible default
    print("=== Stooq (no key) ===")
    for pair in args.ohlcv:
        stooq_sym, repo_sym = pair.split(":")
        try:
            pull_ohlcv(stooq_sym, repo_sym)
        except Exception as e:
            print(f"  ! {pair}: {e}")
    if args.macro:
        build_macro()
    print("Done. Note: Stooq is DAILY (D1). For intraday gold use histdata.com; for crypto use data/pull_open_data.py (Binance).")


if __name__ == "__main__":
    main()

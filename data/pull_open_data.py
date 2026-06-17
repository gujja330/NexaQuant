# data/pull_open_data.py
"""
Pull DEEP, FREE, open-source history so the models stop starving.

Two sources, both free and key-less:
  * Binance  (data.binance.vision)  -> BTC: 1m/5m/15m/1h/4h/1d back to 2017.
                                       Gives multiple regimes (2018 bear, 2021 bull,
                                       2022 crash) and tens of thousands of bars.
  * HistData (histdata.com)          -> Gold/FX 1-minute bars back ~2000 (see note).

Output matches the repo convention -> data/raw/<SYMBOL>_<TF>.parquet, so every probe
(edge / smc / regime / meta_label / validation) auto-includes the new data.

Run examples (needs network):
  python data/pull_open_data.py --binance BTCUSDT --since 2020-01 --tfs 1h 4h 1d 15m
  python data/pull_open_data.py --binance BTCUSDT --since 2018-01 --tfs 5m   # big, slow
"""
import argparse
import io
import sys
import zipfile
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

# Binance interval string -> our timeframe label (file suffix)
TF_MAP = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1", "1w": "W1"}
BINANCE_KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                      "qav", "trades", "tbbav", "tbqav", "ignore"]


def _months(since):
    y, m = map(int, since.split("-"))
    today = date.today()
    out = []
    while (y, m) <= (today.year, today.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def pull_binance(pair, interval, since):
    """Download monthly kline zips from data.binance.vision and concat to OHLCV."""
    frames = []
    for ym in _months(since):
        url = f"https://data.binance.vision/data/spot/monthly/klines/{pair}/{interval}/{pair}-{interval}-{ym}.zip"
        try:
            r = requests.get(url, timeout=60)
            if r.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    df = pd.read_csv(f, header=None, names=BINANCE_KLINE_COLS)
            frames.append(df)
            print(f"    {pair} {interval} {ym}: {len(df)} bars")
        except Exception as e:
            print(f"    ! {pair} {interval} {ym}: {e}")
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    # Binance open_time is ms (older dumps, ~1.7e12) OR us (2025+ dumps, ~1.7e15) and the
    # two can be MIXED across months -> normalise per row to milliseconds.
    ot = pd.to_numeric(df["open_time"], errors="coerce")
    ot = ot.where(ot < 1e14, ot // 1000)            # values > 1e14 are microseconds -> ms
    df = df.assign(time=pd.to_datetime(ot, unit="ms")).set_index("time").sort_index()
    # build on the SAME (time) index so columns align — .astype on aligned series
    out = pd.DataFrame(index=df.index)
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(df[c], errors="coerce")
    out["tick_volume"] = pd.to_numeric(df["trades"], errors="coerce")
    out["spread"] = 0.0
    out["real_volume"] = pd.to_numeric(df["volume"], errors="coerce")
    out = out[~out.index.duplicated(keep="first")].dropna(subset=["close"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binance", default="BTCUSDT", help="Binance pair, e.g. BTCUSDT")
    ap.add_argument("--symbol", default="BTCUSDm", help="repo symbol name for output files")
    ap.add_argument("--since", default="2020-01", help="YYYY-MM start month")
    ap.add_argument("--tfs", nargs="+", default=["1h", "4h", "1d", "15m"], help="Binance intervals")
    args = ap.parse_args()

    print(f"=== Binance {args.binance} since {args.since} -> {args.symbol} ===")
    for interval in args.tfs:
        if interval not in TF_MAP:
            print(f"  ! unknown interval {interval} (skip)"); continue
        df = pull_binance(args.binance, interval, args.since)
        if df is None or df.empty:
            print(f"  ! no data for {interval}"); continue
        out = RAW / f"{args.symbol}_{TF_MAP[interval]}.parquet"
        df.to_parquet(out)
        print(f"  saved {out}  ({len(df)} bars, {df.index[0].date()} -> {df.index[-1].date()})")
    print("\nDone. Re-run any probe (e.g. research/regime_gated_probe.py) to include the new data.")
    print("Gold deep history: download XAUUSD 1m monthly CSVs from histdata.com, then load")
    print("them into data/raw/XAUUSDm_M1.parquet with a DatetimeIndex named 'time'.")


if __name__ == "__main__":
    main()

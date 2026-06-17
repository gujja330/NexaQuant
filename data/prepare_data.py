# data/prepare_data.py
"""
Data preparation for the gold (XAUUSDm) multi-timeframe stack.

We have from the broker pull: H1, H4, D1.
- W1 (weekly) is resampled here from D1 -- this is exact and leakage-free.
- M15 / M5 (the EXECUTION timeframes) are NOT in the repo yet. They must be
  pulled from MT5. A documented stub + instructions are written so the pipeline
  knows exactly what is missing.

Run: python data/prepare_data.py
"""
import pandas as pd
from pathlib import Path

RAW = Path("data/raw")
OHLC_AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
            "tick_volume": "sum", "spread": "mean", "real_volume": "sum"}


def resample_w1_from_d1():
    d1 = pd.read_parquet(RAW / "XAUUSDm_D1.parquet").sort_index()
    # 'W-MON' weekly bars labelled at week end; only fully-closed columns aggregated
    w1 = d1.resample("W-FRI").agg(OHLC_AGG).dropna(subset=["open"])
    out = RAW / "XAUUSDm_W1.parquet"
    w1.to_parquet(out)
    print(f"  W1 resampled from D1 -> {out}  ({len(w1)} weekly bars, "
          f"{w1.index[0].date()} -> {w1.index[-1].date()})")
    return w1


def report_missing_execution_data():
    print("\n  EXECUTION-TIMEFRAME DATA STATUS (needed for 5m/15m entries):")
    for tf in ("M15", "M5"):
        p = RAW / f"XAUUSDm_{tf}.parquet"
        status = "PRESENT" if p.exists() else "MISSING  <-- pull from MT5"
        print(f"    {tf:<4} {status}")
    print("\n  To pull M5/M15 (Windows + MT5 terminal logged in):")
    print("    import MetaTrader5 as mt5; mt5.initialize()")
    print("    rates = mt5.copy_rates_range('XAUUSDm', mt5.TIMEFRAME_M5, start, end)")
    print("    Save as data/raw/XAUUSDm_M5.parquet with a DatetimeIndex named 'time'.")


if __name__ == "__main__":
    print("=== preparing data/raw ===")
    resample_w1_from_d1()
    report_missing_execution_data()

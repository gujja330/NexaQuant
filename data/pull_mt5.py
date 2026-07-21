# data/pull_mt5.py
"""
Pull OHLCV history from MetaTrader 5 for the NexaQuant instruments and timeframes.

RUN THIS ON YOUR WINDOWS MACHINE with the MT5 terminal installed and LOGGED IN.
It cannot run in a headless/CI environment. It writes data/raw/<SYMBOL>_<TF>.parquet
files that all the research probes auto-discover.

Credentials: read from environment (never hardcode). In PowerShell:
    $env:MT5_LOGIN="<your_login>"; $env:MT5_PASSWORD="<your_password>"; $env:MT5_SERVER="<your_server>"
    python data/pull_mt5.py

Symbols/timeframes are taken from configs/base_config.yaml so there is zero hardcoding.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

# how much history to request per timeframe (bars). Lower TFs need more bars.
BARS = {"M5": 200_000, "M15": 120_000, "H1": 60_000, "H4": 20_000, "D1": 5_000, "W1": 1_500}


def load_cfg():
    with open(ROOT / "config" / "base_config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("MetaTrader5 package not installed. Run: pip install MetaTrader5 (Windows only).")

    cfg = load_cfg()
    sysc = cfg["system"]
    # symbols: gold + BTC (extend in configs/base_config.yaml -> system.symbols)
    symbols = sysc.get("symbols", ["XAUUSDm"])
    if "BTCUSDm" not in symbols:
        symbols = symbols + ["BTCUSDm"]
    # all timeframes we want = analysis + execution
    want_tfs = list(dict.fromkeys(sysc.get("analysis_timeframes", []) +
                                  sysc.get("execution_timeframes", []) +
                                  sysc.get("timeframes", [])))
    tf_map = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1,
              "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1}

    def _resolve(env_key, cfg_val):
        v = os.environ.get(env_key) or cfg_val
        return None if (v is None or str(v).startswith("${")) else v

    login = _resolve("MT5_LOGIN", sysc["mt5"].get("login"))
    password = _resolve("MT5_PASSWORD", None)
    server = _resolve("MT5_SERVER", sysc["mt5"].get("server"))
    if not (login and password and server):
        sys.exit("Set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in your environment before running "
                 "(credentials are intentionally not stored in the repo).")

    if not mt5.initialize(login=int(login), password=password, server=server,
                          timeout=sysc["mt5"].get("timeout", 30000)):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")
    print(f"Connected to {server} as {login}")

    for sym in symbols:
        if not mt5.symbol_select(sym, True):
            print(f"  ! could not select {sym} (skipping) -- check symbol name in Market Watch")
            continue
        for tf in want_tfs:
            if tf not in tf_map:
                continue
            n = BARS.get(tf, 50_000)
            rates = mt5.copy_rates_from_pos(sym, tf_map[tf], 0, n)
            if rates is None or len(rates) == 0:
                print(f"  ! {sym} {tf}: no data ({mt5.last_error()})")
                continue
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df.set_index("time").sort_index()
            keep = [c for c in ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
                    if c in df.columns]
            out = RAW / f"{sym}_{tf}.parquet"
            df[keep].to_parquet(out)
            print(f"  saved {sym} {tf:<3} {len(df):>7} bars  {df.index[0].date()} -> {df.index[-1].date()}")

    mt5.shutdown()
    print("Done. Now run: python research/edge_probe.py / smc_probe.py / regime_gated_probe.py")


if __name__ == "__main__":
    main()

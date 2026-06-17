# runners/bootstrap_symbols.py
import os
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timedelta

def main():
    symbol = "XAUUSDm"
    timeframes = ["H1", "H4", "D1"]
    tf_map = {"H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1}

    print("🚀 Bootstrapping with FULL REAL MT5 Data")

    if not mt5.initialize():
        raise RuntimeError("❌ MT5 init failed")

    try:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"❌ Symbol {symbol} not available")

        os.makedirs("data_engine/clean", exist_ok=True)

        # Get symbol info to determine available history
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise RuntimeError(f"❌ No info for {symbol}")

        # Use a safe date range (last 2 years)
        utc_from = datetime.now() - timedelta(days=730)
        utc_to = datetime.now()

        for tf_str in timeframes:
            print(f"📥 Fetching {symbol} {tf_str}...")
            
            # 🔥 Use copy_rates_range instead of copy_rates_from_pos
            rates = mt5.copy_rates_range(symbol, tf_map[tf_str], utc_from, utc_to)
            
            print(f"   Raw rates: {rates is not None}, length: {len(rates) if rates is not None else 0}")
            if rates is None or len(rates) == 0:
                print(f"   ❌ Last error: {mt5.last_error()}")
                continue  # or raise

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)

            from data_engine.event_injector import EventInjector
            injector = EventInjector(config={})  # or load real config if needed
            df = injector.inject_events_into_real_data(symbol, df)

            df.to_parquet(f"data_engine/clean/{symbol}_{tf_str}.parquet")
            print(f"✅ Saved {len(df):,} bars")

    finally:
        mt5.shutdown()
        print("✅ Done")

if __name__ == "__main__":
    main()
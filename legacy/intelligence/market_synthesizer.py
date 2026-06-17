# intelligence/market_synthesizer.py
import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any
import logging
from copulas.multivariate import GaussianMultivariate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketSynthesizer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbols = config["system"]["symbols"]
        self.timeframes = config["system"]["timeframes"]
        self.output_dir = os.path.join("data_engine", "synthetic_enhanced")
        self.synthetic_days = config.get("synthetic", {}).get("days", 730)
        self.risk_profiles = config.get("risk_profiles", {})
        os.makedirs(self.output_dir, exist_ok=True)

    def _generate_base_series(self, symbol: str, length: int) -> pd.DataFrame:
        profile_key = f"{symbol}_risk_profile"
        if profile_key not in self.risk_profiles:
            raise ValueError(f"Risk profile missing for symbol: {symbol}")
        
        profile = self.risk_profiles[profile_key]
        base_price = profile.get("base_price", 100.0)
        base_vol = profile.get("base_volatility", 0.01)
        drift = profile.get("drift", 0.0001)
        spread = profile.get("spread", 0.001)
        
        min_price = max(0.1, base_price * 0.1)
        max_price = base_price * 10.0
        
        vol = base_vol * np.random.uniform(0.8, 1.5)
        returns = np.random.normal(drift, vol, length)
        
        prices = [base_price]
        for r in returns:
            new_price = prices[-1] * np.exp(r)
            new_price = np.clip(new_price, min_price, max_price)
            prices.append(new_price)
        prices = prices[1:]

        volatility = np.abs(returns)
        if np.mean(volatility) > 1e-8:
            tick_volume = (volatility / np.mean(volatility)) * 5000
        else:
            tick_volume = np.full_like(volatility, 5000)
        tick_volume = np.clip(tick_volume, 100, 50000).astype(int)

        index = pd.date_range(end=datetime.now(), periods=length, freq='h')
        df = pd.DataFrame({
            'close': prices,
            'open': prices,
            'high': prices,
            'low': prices,
            'tick_volume': tick_volume
        }, index=index)

        df['open'] = df['close'].shift(1).fillna(df['close'].iloc[0])
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.abs(np.random.normal(0, spread, len(df))))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.abs(np.random.normal(0, spread, len(df))))
        df['symbol'] = symbol
        return df

    def _inject_cross_asset_dependencies(self, dfs: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        if len(dfs) < 2:
            return dfs

        common_index = next(iter(dfs.values())).index
        returns = {}
        for sym, df in dfs.items():
            df_aligned = df.reindex(common_index, method='ffill')
            returns[sym] = df_aligned['close'].pct_change().dropna()

        returns_df = pd.DataFrame(returns).dropna()
        if len(returns_df) < 100:
            logger.warning("Insufficient data for copula fitting, skipping cross-asset dependencies")
            return dfs

        try:
            copula = GaussianMultivariate()
            copula.fit(returns_df)
            synthetic_returns = copula.sample(len(returns_df))
            synthetic_returns.index = returns_df.index

            for sym in dfs:
                if sym in synthetic_returns.columns:
                    cum_returns = (1 + synthetic_returns[sym]).cumprod()
                    base_price = dfs[sym]['close'].iloc[0]
                    dfs[sym]['close'] = base_price * cum_returns
                    
                    profile = self.risk_profiles.get(f"{sym}_risk_profile", {})
                    spread = profile.get("spread", 0.001)
                    dfs[sym]['open'] = dfs[sym]['close'].shift(1).fillna(dfs[sym]['close'].iloc[0])
                    dfs[sym]['high'] = dfs[sym][['open', 'close']].max(axis=1) * (1 + np.abs(np.random.normal(0, spread, len(dfs[sym]))))
                    dfs[sym]['low'] = dfs[sym][['open', 'close']].min(axis=1) * (1 - np.abs(np.random.normal(0, spread, len(dfs[sym]))))
        except Exception as e:
            logger.warning(f"Copula fitting failed: {e}. Using independent series.")
        
        return dfs

    def _inject_economic_events(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        from data_engine.event_injector import EventInjector
        injector = EventInjector(self.config)
        return injector.inject_events_into_synthetic_data(symbol, df)

    def generate_synthetic_datasets(self):
        logger.info("🧠 Generating AI-driven synthetic market data with copula dependencies...")

        raw_dfs = {}
        for symbol in self.symbols:
            df = self._generate_base_series(symbol, self.synthetic_days * 24)
            raw_dfs[symbol] = df

        dependent_dfs = self._inject_cross_asset_dependencies(raw_dfs)

        for symbol, df in dependent_dfs.items():
            df = self._inject_economic_events(df, symbol)
            for tf in self.timeframes:
                if tf == "H1":
                    tf_df = df.copy()
                elif tf == "H4":
                    tf_df = df.resample('4h').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'tick_volume': 'sum',
                        'symbol': 'last'
                    }).dropna()
                elif tf == "D1":
                    tf_df = df.resample('D').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'tick_volume': 'sum',
                        'symbol': 'last'
                    }).dropna()
                else:
                    continue

                path = os.path.join(self.output_dir, f"{symbol}_{tf}.parquet")
                tf_df.to_parquet(path)
                logger.info(f"💾 Saved synthetic {symbol} {tf} → {path}")

        logger.info("✅ Synthetic data generation complete with tail-risk realism and cross-asset dynamics.")
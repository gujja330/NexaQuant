import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any
from arch import arch_model
from hmmlearn import hmm
from scipy import stats
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyntheticGenerator:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Generate institutional-quality synthetic market data with regime-switching and microstructure.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./data_engine/synthetic/"
        os.makedirs(self.output_dir, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def generate_jump_diffusion_prices(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Generate realistic prices using jump-diffusion with regime switching."""
        # Get symbol-specific parameters from config
        symbol_config = self.config.get("symbol_parameters", {}).get(symbol, {})
        mu = symbol_config.get("drift", 0.0002)
        sigma = symbol_config.get("volatility", 0.02)
        jump_intensity = symbol_config.get("jump_intensity", 0.01)
        jump_mean = symbol_config.get("jump_mean", 0.0)
        jump_std = symbol_config.get("jump_std", 0.05)
        
        # Generate base returns with GARCH volatility clustering
        garch_order = self.config.get("synthetic", {}).get("garch_order", [1, 1])
        try:
            am = arch_model(None, vol='Garch', p=garch_order[0], q=garch_order[1])
            sim_data = am.simulate([0.0001, 0.05, 0.85, 0.1], nobs=days)
            returns = sim_data.data.values
        except Exception as e:
            logger.warning(f"GARCH simulation failed for {symbol}: {e}. Using normal returns.")
            returns = np.random.normal(mu, sigma, days)
        
        # Add jump component
        jump_events = np.random.poisson(jump_intensity, days)
        jump_sizes = np.random.normal(jump_mean, jump_std, days)
        jump_returns = jump_events * jump_sizes
        total_returns = returns + jump_returns
        
        # Convert to prices
        last_price = self._get_last_real_price(symbol)
        prices = [last_price]
        for r in total_returns:
            prices.append(prices[-1] * (1 + r))
        prices = prices[1:]
        
        # Create DataFrame
        dates = pd.date_range(start=pd.Timestamp.now() - pd.Timedelta(days=days), periods=days, freq='D')
        df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
            'close': prices,
            'tick_volume': np.random.randint(1000, 50000, days),
            'symbol': symbol,
            'timeframe': 'D1'
        }).set_index('time')
        
        return df

    def _get_last_real_price(self, symbol: str) -> float:
        """Get last real price from stored data or default."""
        try:
            real_path = f"data_engine/clean/{symbol}_D1.parquet"
            if os.path.exists(real_path):
                df = pd.read_parquet(real_path)
                return float(df['close'].iloc[-1])
        except Exception as e:
            logger.warning(f"Could not get real price for {symbol}: {e}")
        # Use config-based defaults if available
        symbol_config = self.config.get("symbol_parameters", {}).get(symbol, {})
        return symbol_config.get("default_price", 1900.0)

    def synthesize_order_flow(self, df: pd.DataFrame) -> pd.DataFrame:
        """Institutional footprint approximation using volume delta and footprint analysis."""
        df = df.copy()
        
        # Volume delta approximation
        df['volume_delta'] = df['tick_volume'] * np.random.choice([-1, 1], size=len(df))
        
        # Footprint-style bid/ask volume distribution
        df['bid_volume'] = df['tick_volume'] * np.random.beta(2, 2, size=len(df))
        df['ask_volume'] = df['tick_volume'] - df['bid_volume']
        
        # Order flow imbalance
        df['order_flow_imbalance'] = (df['bid_volume'] - df['ask_volume']) / df['tick_volume']
        
        return df

    def model_microstructure(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bid-ask dynamics and liquidity patterns simulation."""
        df = df.copy()
        
        # Bid-ask spread approximation
        symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else "UNKNOWN"
        symbol_config = self.config.get("symbol_parameters", {}).get(symbol, {})
        base_spread_pct = symbol_config.get("base_spread_pct", 0.0005)
        df['spread'] = df['close'] * base_spread_pct * (1 + np.random.exponential(0.2, size=len(df)))
        
        # Liquidity measure
        df['liquidity'] = np.random.gamma(2, 1000, size=len(df))
        
        # Market impact approximation
        df['kyle_lambda'] = np.random.exponential(0.01, size=len(df))
        
        return df

    def generate_regime_switching_data(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Generate data with HMM regime switching for realistic market states."""
        # First generate base prices
        df = self.generate_jump_diffusion_prices(symbol, days)
        
        # Fit HMM to add regime switching
        try:
            returns = df['close'].pct_change().dropna().values.reshape(-1, 1)
            if len(returns) > 50:
                n_components = self.config.get("regime_detection", {}).get("n_components", 3)
                model = hmm.GaussianHMM(n_components=n_components, covariance_type="full", n_iter=100)
                model.fit(returns)
                hidden_states = model.predict(returns)
                
                # Adjust volatility by regime
                regime_volatilities = [0.5, 1.0, 2.0]  # Low, medium, high volatility regimes
                for i, state in enumerate(hidden_states):
                    if i < len(df):
                        vol_multiplier = regime_volatilities[min(state, len(regime_volatilities)-1)]
                        # Apply regime-specific volatility adjustment
                        noise = np.random.normal(0, 0.001 * (vol_multiplier - 1))
                        df.iloc[i, df.columns.get_loc('close')] *= (1 + noise)
        except Exception as e:
            logger.warning(f"HMM regime switching failed for {symbol}: {e}")
        
        return df

    def generate_synthetic_dataset(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Complete synthetic dataset generation pipeline."""
        # Generate regime-switching prices
        df = self.generate_regime_switching_data(symbol, days)
        
        # Add microstructure
        df = self.model_microstructure(df)
        
        # Add order flow
        df = self.synthesize_order_flow(df)
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, f"{symbol}_D1_synthetic.parquet")
        df.to_parquet(output_path)
        logger.info(f"Saved synthetic dataset to {output_path}")
        
        return df
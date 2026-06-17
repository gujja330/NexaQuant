import os
import yaml
import numpy as np
import pandas as pd
from typing import Dict, Any
from scipy.optimize import minimize
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Advanced portfolio optimization with risk constraints and regime awareness.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.risk_budget = self.config["system"]["risk_per_trade"]
        self.max_position_size = self.config.get("risk_fortress", {}).get("max_position_size", 10.0)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def optimize_risk_parity(self, volatilities: np.ndarray) -> np.ndarray:
        """Volatility-adjusted risk parity allocation."""
        if len(volatilities) == 0:
            return np.array([])
        
        # Risk parity: equal risk contribution
        inv_vol = 1.0 / volatilities
        weights = inv_vol / np.sum(inv_vol)
        return weights

    def optimize_mean_variance(self, expected_returns: np.ndarray, cov_matrix: np.ndarray, risk_aversion: float = 1.0) -> np.ndarray:
        """Mean-variance optimization with risk aversion parameter."""
        n_assets = len(expected_returns)
        if n_assets == 0:
            return np.array([])
        
        def objective(weights):
            portfolio_return = np.dot(weights, expected_returns)
            portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            return -(portfolio_return - risk_aversion * portfolio_risk)
        
        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        bounds = [(0, 1) for _ in range(n_assets)]
        initial_weights = np.ones(n_assets) / n_assets
        
        result = minimize(objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        return result.x if result.success else initial_weights

    def apply_position_constraints(self, weights: np.ndarray, agent_signals: np.ndarray) -> np.ndarray:
        """Apply position sizing constraints based on agent confidence and risk limits."""
        constrained_weights = weights.copy()
        
        # Scale by agent signal strength
        signal_strength = np.abs(agent_signals)
        constrained_weights = constrained_weights * signal_strength
        
        # Apply max position size constraint
        max_weight = self.max_position_size / 100.0  # Convert to decimal
        constrained_weights = np.clip(constrained_weights, 0, max_weight)
        
        # Renormalize
        if np.sum(constrained_weights) > 0:
            constrained_weights = constrained_weights / np.sum(constrained_weights)
        
        return constrained_weights

    def optimize_portfolio(self, 
                          agent_signals: Dict[str, float], 
                          volatilities: Dict[str, float],
                          correlations: np.ndarray = None) -> Dict[str, float]:
        """Complete portfolio optimization pipeline."""
        symbols = list(agent_signals.keys())
        if len(symbols) == 0:
            return {}
        
        # Convert to arrays
        signals_array = np.array([agent_signals[s] for s in symbols])
        vols_array = np.array([volatilities.get(s, 0.02) for s in symbols])
        
        # Risk parity optimization
        weights = self.optimize_risk_parity(vols_array)
        
        # Apply constraints
        constrained_weights = self.apply_position_constraints(weights, signals_array)
        
        # Convert back to dictionary
        optimized_portfolio = {}
        for i, symbol in enumerate(symbols):
            optimized_portfolio[symbol] = float(constrained_weights[i])
        
        logger.info(f"Optimized portfolio: {optimized_portfolio}")
        return optimized_portfolio
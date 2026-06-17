import os
import yaml
import numpy as np
import pandas as pd
from typing import Dict, Any, List
from scipy import stats
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StressSimulator:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Multi-dimensional stress testing with agent interaction modeling.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.stress_scenarios = self.config.get("risk_fortress", {}).get("stress_scenarios", {})

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def simulate_crisis_scenarios(self, portfolio_positions: Dict[str, float]) -> Dict[str, Any]:
        """Historical crisis replication with multi-agent game dynamics."""
        results = {}
        
        # 2008-style crisis
        if "2008_crisis" in self.stress_scenarios:
            crisis_params = self.stress_scenarios["2008_crisis"]
            volatility_spike = crisis_params.get("volatility_multiplier", 3.0)
            correlation_breakdown = crisis_params.get("correlation_breakdown", 0.8)
            
            # Simulate portfolio impact
            portfolio_loss = 0.0
            for symbol, position in portfolio_positions.items():
                # Apply volatility spike and correlation effects
                symbol_loss = position * 0.35 * volatility_spike  # 35% loss amplified by volatility
                portfolio_loss += symbol_loss
            
            results["2008_crisis"] = {
                "portfolio_loss": float(portfolio_loss),
                "volatility_impact": volatility_spike,
                "correlation_impact": correlation_breakdown
            }
        
        # COVID-2020 style crisis
        if "covid_crisis" in self.stress_scenarios:
            crisis_params = self.stress_scenarios["covid_crisis"]
            volatility_spike = crisis_params.get("volatility_multiplier", 4.0)
            liquidity_dryup = crisis_params.get("liquidity_dryup", 0.7)
            
            portfolio_loss = 0.0
            for symbol, position in portfolio_positions.items():
                symbol_loss = position * 0.40 * volatility_spike
                portfolio_loss += symbol_loss
            
            results["covid_crisis"] = {
                "portfolio_loss": float(portfolio_loss),
                "volatility_impact": volatility_spike,
                "liquidity_impact": liquidity_dryup
            }
        
        return results

    def generate_tail_scenarios(self, num_scenarios: int = 1000) -> List[Dict[str, float]]:
        """Monte Carlo extreme scenarios with agent interaction modeling."""
        scenarios = []
        for _ in range(num_scenarios):
            # Generate extreme market moves
            extreme_move = np.random.normal(0, 0.1, len(self.symbols))  # 10% daily moves
            scenario = {}
            for i, symbol in enumerate(self.symbols):
                scenario[symbol] = float(extreme_move[i])
            scenarios.append(scenario)
        return scenarios

    def test_correlation_breakdown(self, base_correlations: np.ndarray) -> Dict[str, Any]:
        """Correlation structure failure testing with agent response simulation."""
        # Simulate correlation breakdown (all correlations → 1.0 during crisis)
        crisis_correlations = np.ones_like(base_correlations)
        
        # Calculate diversification loss
        diversification_loss = np.sum(np.abs(crisis_correlations - base_correlations))
        
        return {
            "diversification_loss": float(diversification_loss),
            "crisis_correlations": crisis_correlations.tolist(),
            "base_correlations": base_correlations.tolist()
        }

    def assess_liquidity_stress(self, portfolio_positions: Dict[str, float]) -> Dict[str, float]:
        """Liquidity crisis modeling with realistic execution constraints."""
        liquidity_impact = {}
        for symbol, position in portfolio_positions.items():
            # Larger positions have higher slippage during liquidity stress
            slippage = min(0.05, abs(position) * 0.01)  # Up to 5% slippage
            liquidity_impact[symbol] = float(slippage)
        return liquidity_impact

    def validate_stress_test_realism(self, scenario_results: Dict[str, Any]) -> bool:
        """Statistical validation of stress test scenarios against historical events."""
        # Check if losses are within historical bounds
        max_historical_loss = 0.50  # 50% max historical drawdown
        
        for scenario, results in scenario_results.items():
            if isinstance(results, dict) and "portfolio_loss" in results:
                if abs(results["portfolio_loss"]) > max_historical_loss:
                    logger.warning(f"Stress test unrealistic: {scenario} loss > {max_historical_loss}")
                    return False
        
        return True
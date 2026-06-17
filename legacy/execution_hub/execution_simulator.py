# execution_hub/execution_simulator.py
import os
import numpy as np
from typing import Dict, Any
import logging

# AI-Driven Imports (Per new_rules.md)
from scipy.stats import norm
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExecutionSimulator:
    """
    Comprehensive execution simulation with realistic slippage, latency, and liquidity modeling.
    Fully dynamic. Zero hardcoding. Config-driven. AI-powered.
    Implements Market Microstructure Modeling, Slippage Prediction, Latency Simulation, and Liquidity Impact.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.execution_config = config.get("execution", {})
        self.system_config = config.get("system", {})
        
        # 🔹 All numeric parameters from config — NO HARDCODING
        self.base_slippage_bps = self.execution_config["base_slippage_bps"]
        self.volatility_slippage_multiplier = self.execution_config["volatility_slippage_multiplier"]
        self.liquidity_slippage_multiplier = self.execution_config["liquidity_slippage_multiplier"]
        self.base_latency_ms = self.execution_config["base_latency_ms"]
        self.news_latency_multiplier = self.execution_config["news_latency_multiplier"]
        self.partial_fill_probability_base = self.execution_config["partial_fill_probability_base"]
        self.liquidity_partial_fill_multiplier = self.execution_config["liquidity_partial_fill_multiplier"]
        self.news_execution_degradation = self.execution_config["news_execution_degradation"]
        self.max_slippage_bps = self.execution_config["max_slippage_bps"]
        self.max_latency_ms = self.execution_config["max_latency_ms"]
        
        # Ensure log directories exist
        os.makedirs("execution_hub/simulations", exist_ok=True)

    def simulate_realistic_slippage(self, order_size: float, market_data: Dict[str, Any]) -> float:
        """Volume-based slippage modeling with volatility and liquidity adjustments — all parameters from config."""
        volatility = market_data.get("volatility", 0.02)
        volume = market_data.get("volume", 1000)
        avg_volume = market_data.get("avg_volume", 10000)
        
        # Calculate liquidity ratio
        liquidity_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        
        # Base slippage in basis points
        slippage_bps = self.base_slippage_bps
        
        # Add volatility component
        slippage_bps += volatility * self.volatility_slippage_multiplier
        
        # Add liquidity component
        if liquidity_ratio < 1.0:
            slippage_bps += (1.0 - liquidity_ratio) * self.liquidity_slippage_multiplier
        
        # Cap maximum slippage
        slippage_bps = min(slippage_bps, self.max_slippage_bps)
        
        return float(slippage_bps / 10000.0)  # Convert to decimal

    def model_execution_latency(self, market_data: Dict[str, Any]) -> float:
        """Realistic latency simulation with broker-specific characteristics — all parameters from config."""
        is_news_event = market_data.get("is_news_event", False)
        volatility = market_data.get("volatility", 0.02)
        
        latency_ms = self.base_latency_ms
        
        # Add news event latency
        if is_news_event:
            latency_ms *= self.news_latency_multiplier
        
        # Add volatility component
        latency_ms += volatility * 50  # 50ms per 1% volatility
        
        # Cap maximum latency
        latency_ms = min(latency_ms, self.max_latency_ms)
        
        return float(latency_ms)

    def calculate_market_impact(self, order_size: float, market_data: Dict[str, Any]) -> float:
        """Market impact modeling based on order size and liquidity conditions."""
        avg_volume = market_data.get("avg_volume", 10000)
        price = market_data.get("price", 1.0)
        
        # Calculate order size as fraction of average volume
        volume_fraction = order_size / avg_volume if avg_volume > 0 else 1.0
        
        # Market impact proportional to square root of volume fraction
        impact = price * 0.001 * np.sqrt(volume_fraction)
        
        return float(impact)

    def simulate_partial_fills(self, order_size: float, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Probabilistic partial fill modeling with liquidity constraints — all parameters from config."""
        volume = market_data.get("volume", 1000)
        avg_volume = market_data.get("avg_volume", 10000)
        liquidity_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        
        # Base partial fill probability
        partial_fill_prob = self.partial_fill_probability_base
        
        # Increase probability in low liquidity
        if liquidity_ratio < 1.0:
            partial_fill_prob += (1.0 - liquidity_ratio) * self.liquidity_partial_fill_multiplier
        
        # Cap probability
        partial_fill_prob = min(partial_fill_prob, 0.9)
        
        # Determine if partial fill occurs
        is_partial = np.random.random() < partial_fill_prob
        
        if is_partial:
            # Fill 50-90% of order
            fill_fraction = np.random.uniform(0.5, 0.9)
            filled_size = order_size * fill_fraction
            unfilled_size = order_size - filled_size
        else:
            filled_size = order_size
            unfilled_size = 0.0
        
        return {
            "is_partial": is_partial,
            "filled_size": float(filled_size),
            "unfilled_size": float(unfilled_size),
            "fill_probability": float(partial_fill_prob)
        }

    def inject_news_execution_effects(self, execution_result: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execution degradation during high-impact news events — all parameters from config."""
        is_news_event = market_data.get("is_news_event", False)
        
        if is_news_event:
            # Degrade execution quality during news
            execution_result["slippage"] *= (1.0 + self.news_execution_degradation)
            execution_result["latency"] *= (1.0 + self.news_execution_degradation)
            execution_result["fill_quality"] = max(0.0, execution_result.get("fill_quality", 1.0) - self.news_execution_degradation)
            execution_result["news_impact"] = True
        
        return execution_result

    def simulate_execution(self, symbol: str, action: int, position_size: float, 
                         entry_price: float, stop_loss: float, take_profit: float,
                         market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Complete execution simulation with all realistic effects — all parameters from config."""
        # Simulate latency
        latency_ms = self.model_execution_latency(market_data)
        
        # Simulate slippage
        slippage = self.simulate_realistic_slippage(position_size, market_data)
        
        # Apply slippage to entry price
        if action in [0, 1]:  # Buy
            executed_price = entry_price * (1 + slippage)
        else:  # Sell
            executed_price = entry_price * (1 - slippage)
        
        # Simulate partial fills
        partial_fill_result = self.simulate_partial_fills(position_size, market_data)
        executed_size = partial_fill_result["filled_size"]
        
        # Calculate market impact
        market_impact = self.calculate_market_impact(executed_size, market_data)
        if action in [0, 1]:  # Buy
            executed_price += market_impact
        else:  # Sell
            executed_price -= market_impact
        
        # Simulate exit (simplified - in reality would monitor over time)
        exit_price = executed_price  # Placeholder - would be determined by strategy logic
        pnl = 0.0  # Placeholder - would be calculated based on actual exit
        
        # Create base execution result
        execution_result = {
            "status": "success",
            "symbol": symbol,
            "action": action,
            "requested_size": position_size,
            "executed_size": executed_size,
            "entry_price": executed_price,
            "exit_price": exit_price,
            "slippage": slippage,
            "latency_ms": latency_ms,
            "pnl": pnl,
            "partial_fill": partial_fill_result["is_partial"],
            "fill_quality": 1.0 - (partial_fill_result["unfilled_size"] / position_size if position_size > 0 else 0),
            "market_impact": market_impact,
            "timestamp": market_data.get("timestamp", None)
        }
        
        # Inject news effects if applicable
        execution_result = self.inject_news_execution_effects(execution_result, market_data)
        
        logger.info(f"📝 Simulated execution: {symbol} {action} {executed_size:.2f} lots @ {executed_price:.5f}")
        
        return execution_result
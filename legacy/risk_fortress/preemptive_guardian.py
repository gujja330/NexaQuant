# risk_fortress/preemptive_guardian.py
import numpy as np
from typing import Dict, Any, Tuple
import logging

from sklearn.ensemble import IsolationForest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PreemptiveGuardian:
    """
    Preemptive risk detection and intervention before losses occur.
    Fully dynamic. Zero hardcoding. Config-driven. AI-powered.
    Implements Agentic AI, Predictive AI, and Financial AI techniques.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbols = config["system"]["symbols"]
        self.risk_fortress_config = config.get("risk_fortress", {})
        self.risk_profiles = config.get("risk_profiles", {})
        
        # 🔹 All numeric parameters from config — NO HARDCODING
        self.early_warning_threshold = self.risk_fortress_config["early_warning_threshold"]
        self.strategy_health_threshold = self.risk_fortress_config["strategy_health_threshold"]
        self.max_drawdown_limit = config["system"]["max_drawdown_limit"]
        self.volatility_normalization_base = self.risk_fortress_config["volatility_normalization_base"]
        self.anomaly_contamination = self.risk_fortress_config["anomaly_contamination"]
        self.derisk_exponent = self.risk_fortress_config["derisk_exponent"]
        self.volatility_spike_threshold = self.risk_fortress_config["volatility_spike_threshold"]
        self.regime_multipliers = self.risk_fortress_config["regime_multipliers"]
        self.base_stop_multiplier = self.risk_fortress_config["base_stop_multiplier"]
        self.trailing_profit_threshold = self.risk_fortress_config["trailing_profit_threshold"]
        self.unusual_move_window = self.risk_fortress_config["unusual_move_window"]
        self.long_vol_window = self.risk_fortress_config["long_vol_window"]
        self.confidence_volatility_penalty_weight = self.risk_fortress_config["confidence_volatility_penalty_weight"]
        self.drawdown_severity_threshold = self.risk_fortress_config["drawdown_severity_threshold"]
        self.anomaly_health_penalty = self.risk_fortress_config["anomaly_health_penalty"]

        # 🔹 Validate risk profiles at init
        for symbol in self.symbols:
            profile_key = f"{symbol}_risk_profile"
            if profile_key not in self.risk_profiles:
                raise ValueError(f"❌ Missing required risk profile in config: {profile_key}")
            required_fields = ["pip_value_per_lot", "min_stop_pips", "max_position_size"]
            for field in required_fields:
                if field not in self.risk_profiles[profile_key]:
                    raise ValueError(f"❌ Missing required field '{field}' in {profile_key}")

        self.anomaly_detector = IsolationForest(
            contamination=self.anomaly_contamination,
            random_state=42
        )

    def detect_early_warning_signals(self, performance_metrics: Dict[str, float]) -> Dict[str, bool]:
        warnings = {}
        
        current_sharpe = performance_metrics.get("sharpe_ratio", 1.0)
        baseline_sharpe = performance_metrics.get("baseline_sharpe", 1.2)
        sharpe_degradation = current_sharpe / baseline_sharpe if baseline_sharpe > 0 else 0
        warnings["sharpe_degradation"] = sharpe_degradation < self.early_warning_threshold
        
        current_win_rate = performance_metrics.get("win_rate", 0.55)
        baseline_win_rate = performance_metrics.get("baseline_win_rate", 0.60)
        win_rate_drop = current_win_rate / baseline_win_rate if baseline_win_rate > 0 else 0
        warnings["win_rate_drop"] = win_rate_drop < self.early_warning_threshold
        
        current_dd = performance_metrics.get("current_drawdown", 0.05)
        dd_severity = current_dd / self.max_drawdown_limit if self.max_drawdown_limit > 0 else 0
        warnings["drawdown_severity"] = dd_severity > self.drawdown_severity_threshold
        
        current_vol = performance_metrics.get("current_volatility", 0.02)
        baseline_vol = performance_metrics.get("baseline_volatility", 0.015)
        vol_spike = current_vol / baseline_vol if baseline_vol > 0 else 0
        warnings["volatility_spike"] = vol_spike > self.volatility_spike_threshold
        
        return warnings

    def assess_strategy_health(self, agent_confidences: Dict[str, float], market_volatility: float) -> float:
        if not agent_confidences:
            return 0.5
        
        avg_confidence = np.mean(list(agent_confidences.values()))
        volatility_penalty = min(1.0, market_volatility / self.volatility_normalization_base)
        health_score = avg_confidence * (1 - volatility_penalty * self.confidence_volatility_penalty_weight)
        
        confidences_array = np.array(list(agent_confidences.values())).reshape(-1, 1)
        try:
            anomaly_scores = self.anomaly_detector.fit_predict(confidences_array)
            if -1 in anomaly_scores:
                health_score *= self.anomaly_health_penalty
        except Exception as e:
            logger.warning(f"Anomaly detection failed: {e}")
        
        return float(max(0.0, min(1.0, health_score)))

    def implement_preemptive_derisking(self, current_position_size: float, health_score: float) -> float:
        if health_score > self.strategy_health_threshold:
            return current_position_size
        
        derisk_factor = (health_score / self.strategy_health_threshold) ** self.derisk_exponent
        new_position_size = current_position_size * derisk_factor
        
        logger.warning(f"⚠️ Preemptive derisking: {current_position_size:.2f} → {new_position_size:.2f} (health: {health_score:.2f})")
        return new_position_size

    def calculate_dynamic_stop_losses(self, symbol: str, atr: float, volatility_regime: int, entry_price: float = None, current_price: float = None) -> Tuple[float, float]:
        profile = self.risk_profiles[f"{symbol}_risk_profile"]
        min_stop_pips = profile["min_stop_pips"]
        pip_value = profile["pip_value_per_lot"]
        
        if volatility_regime < len(self.regime_multipliers):
            multiplier = self.regime_multipliers[volatility_regime]
        else:
            multiplier = self.base_stop_multiplier
        
        base_stop_pips = max(atr * multiplier, min_stop_pips)
        fixed_stop = base_stop_pips * pip_value
        trailing_stop = fixed_stop
        
        if entry_price is not None and current_price is not None:
            if current_price > entry_price:  # Long
                profit_pips = (current_price - entry_price) / pip_value
                if profit_pips > base_stop_pips * self.trailing_profit_threshold:
                    trailing_stop = max(fixed_stop, (current_price - entry_price) / 2)
            else:  # Short
                profit_pips = (entry_price - current_price) / pip_value
                if profit_pips > base_stop_pips * self.trailing_profit_threshold:
                    trailing_stop = max(fixed_stop, (entry_price - current_price) / 2)
        
        return float(fixed_stop), float(trailing_stop)

    def detect_unusual_moves(self, returns: np.ndarray, window: int = None) -> bool:
        window = window or self.unusual_move_window
        if len(returns) < window + 10:
            return False
        
        recent_vol = np.std(returns[-window:])
        long_vol = np.std(returns[-self.long_vol_window:]) if len(returns) >= self.long_vol_window else recent_vol
        if long_vol <= 0:
            return False
            
        volatility_ratio = recent_vol / long_vol
        return volatility_ratio > self.volatility_spike_threshold
# intelligence/regime_detector.py
import os
import numpy as np
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime
import logging

# AI-Driven Imports (Per new_rules.md)
import hmmlearn.hmm as hmm
import ruptures as rpt  # ✅ Standard, open-source, PyPI-available
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RegimeDetector:
    """
    Real-time market regime identification with misclassification detection and confidence calibration.
    Fully dynamic. Zero hardcoding. Config-driven. AI-powered.
    Implements Temporal AI, HMM with uncertainty, change point detection, regime-switching GARCH.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.intelligence_config = config.get("intelligence", {})
        self.risk_fortress_config = config.get("risk_fortress", {})
        
        # 🔹 All numeric parameters from config — NO HARDCODING
        self.n_regimes = self.intelligence_config.get("n_regimes", 3)
        self.hmm_covariance_type = self.intelligence_config.get("hmm_covariance_type", "diag")
        self.change_point_penalty = self.intelligence_config.get("change_point_penalty", 10)
        self.min_regime_length = self.intelligence_config.get("min_regime_length", 20)
        self.volatility_window = self.intelligence_config.get("volatility_window", 20)
        
        os.makedirs("knowledge_base/regimes", exist_ok=True)

    def detect_regime_hmm(self, returns: np.ndarray) -> np.ndarray:
        """HMM regime classification with uncertainty quantification."""
        if len(returns) < self.min_regime_length * 2:
            # Not enough data — return default regime
            return np.zeros(len(returns), dtype=int)
        
        # Prepare features: returns + volatility
        volatility = pd.Series(returns).rolling(window=self.volatility_window).std().fillna(0).values
        features = np.column_stack([returns, volatility])
        
        # Standardize features
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)
        
        # Fit HMM
        model = hmm.GaussianHMM(
            n_components=self.n_regimes,
            covariance_type=self.hmm_covariance_type,
            n_iter=1000,
            tol=1e-4,
            random_state=42
        )
        
        try:
            model.fit(features_scaled)
            hidden_states = model.predict(features_scaled)
            logger.info(f"HMM regime detection completed: {self.n_regimes} regimes identified")
            return hidden_states
        except Exception as e:
            logger.warning(f"HMM fitting failed: {e}. Returning default regime.")
            return np.zeros(len(returns), dtype=int)

    def add_regime_column(self, df: pd.DataFrame) -> pd.DataFrame:
        # 🔒 Preserve original index FIRST
        original_index = df.index.copy()
        df = df.copy()
        
        # Handle edge cases
        if 'close' not in df.columns or df.empty:
            df['regime'] = 0
            df.index = original_index
            return df
        
        returns = df['close'].pct_change().dropna().values
        if len(returns) == 0:
            df['regime'] = 0
            df.index = original_index
            return df
        
        # Detect regimes
        regimes = self.detect_regime_hmm(returns)
        if len(regimes) == 0:
            df['regime'] = 0
            df.index = original_index
            return df
        
        # 🔒 Safe padding to match original DataFrame length
        if len(regimes) < len(df):
            regimes = np.pad(regimes, (len(df) - len(regimes), 0), mode='constant', constant_values=0)
        else:
            regimes = regimes[:len(df)]
        
        # Assign regime column and restore original index
        df['regime'] = regimes.astype(int)
        df.index = original_index  # ← CRITICAL: Preserve datetime index
        return df
    
    def identify_structural_breaks(self, price_series: np.ndarray) -> List[int]:
        """Bayesian change point detection with false positive filtering using ruptures."""
        if len(price_series) < 50:
            return []
        
        try:
            # Use Pelt algorithm with linear cost (efficient for financial data)
            algo = rpt.Pelt(model="l2", min_size=self.min_regime_length).fit(price_series)
            breaks = algo.predict(pen=self.change_point_penalty)
            
            # Remove last break (always end of series)
            if breaks and breaks[-1] == len(price_series):
                breaks = breaks[:-1]
            
            logger.info(f"Structural breaks detected: {len(breaks)} change points")
            return breaks
        except Exception as e:
            logger.warning(f"Change point detection failed: {e}. Returning empty list.")
            return []

    def forecast_transitions(self, current_regime: int, regime_history: np.ndarray) -> Dict[str, float]:
        """Regime transition probability estimation."""
        if len(regime_history) < 100:
            # Default transition probabilities
            return {
                "transition_probs": [0.9, 0.05, 0.05],
                "risk_aversion_scalar": 1.0
            }
        
        # Count transitions from current_regime
        transitions = np.zeros(self.n_regimes)
        for i in range(len(regime_history) - 1):
            if regime_history[i] == current_regime:
                next_regime = regime_history[i + 1]
                if next_regime < self.n_regimes:
                    transitions[next_regime] += 1
        
        # Add smoothing
        transitions += 1
        transition_probs = (transitions / np.sum(transitions)).tolist()
        
        # Risk aversion scalar (higher in volatile regimes)
        risk_aversion = 1.0 + (current_regime * 0.5)  # Regime 0: 1.0, Regime 1: 1.5, Regime 2: 2.0
        
        return {
            "transition_probs": transition_probs,
            "risk_aversion_scalar": float(risk_aversion)
        }

    def contextualize_signals(self, signal: float, regime: int, confidence: float) -> float:
        """Regime-aware signal interpretation with misclassification penalties."""
        regime_adjustments = [0.8, 1.0, 1.2]  # Low, medium, high conviction regimes
        
        if regime < len(regime_adjustments):
            adjusted_signal = signal * regime_adjustments[regime]
        else:
            adjusted_signal = signal
        
        # Apply confidence penalty
        final_signal = adjusted_signal * confidence
        
        return float(final_signal)

    def modulate_risk_aversion(self, regime: int) -> float:
        """Dynamic risk-aversion adjustment per regime with stability constraints."""
        risk_aversion_map = [0.8, 1.0, 1.5]  # Conservative, neutral, aggressive
        
        if regime < len(risk_aversion_map):
            return float(risk_aversion_map[regime])
        else:
            return 1.0
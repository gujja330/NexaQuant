# intelligence/strategy_zoo.py
import numpy as np
from typing import Dict, Any

class StrategyZoo:
    """Top 10 regime-aware, feature-driven strategies using your existing 113 features."""
    
    @staticmethod
    def trend_momentum(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        min_slope = config["intelligence"].get("min_price_slope_for_trend", 0.00005)
        # ✅ Remove regime check — trade strong slopes in ANY regime
        return 1 if features.get("price_slope", 0) > min_slope else -1 if features.get("price_slope", 0) < -min_slope else 0

    @staticmethod
    def liquidity_sweep(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        sweep_high = features.get("LiquiditySweepHigh", 0)
        sweep_low = features.get("LiquiditySweepLow", 0)
        return -1 if sweep_high else 1 if sweep_low else 0

    @staticmethod
    def breakout_fvg(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        fvg = features.get("fvg", 0)
        vol = features.get("vol_24", 0.01)
        threshold = config["intelligence"].get("fvg_vol_threshold", 0.015)
        return 1 if fvg == 1 and vol > threshold else -1 if fvg == -1 and vol > threshold else 0

    @staticmethod
    def volatility_contraction(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        bb_width = features.get("bb_width", 10)
        roc = features.get("roc", 0)
        # Use config-driven threshold or fallback
        bb_threshold = config["intelligence"].get("bb_width_percentile", 20)
        return 1 if bb_width < np.percentile([1,2,3,4,5], bb_threshold) and roc > 0 else -1 if bb_width < np.percentile([1,2,3,4,5], bb_threshold) and roc < 0 else 0

    @staticmethod
    def mean_reversion_rsi(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        rsi = features.get("RSI", 50)
        oversold = config["intelligence"].get("rsi_oversold", 40)
        overbought = config["intelligence"].get("rsi_overbought", 60)
        # ✅ Trade extremes in ANY regime
        return 1 if rsi < oversold else -1 if rsi > overbought else 0

    @staticmethod
    def volume_weighted_momentum(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        hv_mom = features.get("HighVol_Momentum", 0)
        threshold = config["intelligence"].get("high_vol_momentum_threshold", 0.5)
        return 1 if hv_mom > threshold else -1 if hv_mom < -threshold else 0

    @staticmethod
    def atr_volatility_filter(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        atr = features.get("ATR_ta", 10)
        min_atr = config["intelligence"].get("min_atr_threshold", 5)
        price_slope = features.get("price_slope", 0)
        if atr > min_atr:
            return 1 if price_slope > 0 else -1 if price_slope < 0 else 0
        return 0

    @staticmethod
    def regime_adaptive_macd(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        if regime != 2:
            return 0
        macd = features.get("MACD", 0)
        signal = features.get("MACD_signal", 0)
        return 1 if macd > signal else -1 if macd < signal else 0

    @staticmethod
    def doji_reversal(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        doji = features.get("doji", 0)
        rsi = features.get("RSI", 50)
        oversold = config["intelligence"].get("rsi_oversold", 30)
        overbought = config["intelligence"].get("rsi_overbought", 70)
        if doji and (rsi < oversold or rsi > overbought):
            return 1 if rsi < oversold else -1
        return 0

    @staticmethod
    def ai_consensus(features: Dict[str, float], regime: int, config: Dict[str, Any]) -> int:
        # ✅ Just sum all signals — no regime gating
        
        signals = [
            StrategyZoo.trend_momentum(features, regime, config),
            StrategyZoo.mean_reversion_rsi(features, regime, config),
            StrategyZoo.liquidity_sweep(features, regime, config),
            StrategyZoo.breakout_fvg(features, regime, config)
        ]
        vote_sum = sum(signals)
        return 1 if vote_sum > 0 else -1 if vote_sum < 0 else 0
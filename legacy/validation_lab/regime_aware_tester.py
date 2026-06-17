# validation_lab/regime_aware_tester.py
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple 
import logging
from datetime import datetime  # 🔥 ADD THIS LINE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RegimeAwareTester:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_config = config.get("validation", {})
        self.execution_config = config.get("execution", {})
        self.brier_score_threshold = self.validation_config.get("brier_score_threshold", 0.25)
        self.execution_latency_ms = self.execution_config.get("latency_ms", 300)
        self.slippage_model = self.execution_config.get("slippage_model", "volume_based")
        os.makedirs("validation_lab/results", exist_ok=True)

    def _safe_isoformat(self, timestamp):
        if isinstance(timestamp, (int, float)):
            return pd.to_datetime(timestamp, unit='s').isoformat()
        elif hasattr(timestamp, 'isoformat'):
            return timestamp.isoformat()
        else:
            try:
                return pd.to_datetime(timestamp).isoformat()
            except:
                return datetime.now().isoformat()

    def _get_pip_value(self, symbol: str) -> float:
        profile_key = f"{symbol}_risk_profile"
        return self.config.get("risk_profiles", {}).get(profile_key, {}).get("pip_value_per_lot", 0.01)

    def _simulate_strategy_trades(self, df: pd.DataFrame, symbol: str, timeframe: str = "H1") -> List[Dict[str, Any]]:
        min_bars_map = {"D1": 30, "H4": 30, "H1": 30}
        min_bars = min_bars_map.get(timeframe, 30)
        if len(df) < min_bars:
            return []

        from intelligence.multi_agent_brain import MultiAgentBrain
        brain = MultiAgentBrain(self.config)

        exclude = {'open', 'high', 'low', 'close', 'tick_volume', 'time', 'symbol', 'raw_close', 'regime'}
        feature_cols = sorted([col for col in df.columns if col not in exclude and np.issubdtype(df[col].dtype, np.number)])

        if not feature_cols:
            logger.warning("No features available for trading")
            return []

        trades = []
        in_position = False
        position_type = None
        entry_price = 0.0

        for i in range(min_bars, len(df)):
            close = df['close'].iloc[i]
            regime = int(df['regime'].iloc[i]) if 'regime' in df.columns else 1
            state = df[feature_cols].iloc[i].values.astype(np.float32)

            try:
                action, meta = brain.act(state=state, regime=regime, feature_names=feature_cols)
            except Exception as e:
                logger.error(f"AI brain failed at step {i}: {e}")
                continue

            if in_position:
                if action == 0 or meta.get("exit_reason"):
                    exit_price = close
                    pip_value = self._get_pip_value(symbol)
                    pnl = (exit_price - entry_price) / pip_value if position_type == 'long' else (entry_price - exit_price) / pip_value
                    trades.append({
                        "timestamp": df.index[i].isoformat(),
                        "symbol": symbol,
                        "action": 1 if position_type == 'long' else -1,
                        "entry_price": float(entry_price),
                        "exit_price": float(exit_price),
                        "pnl": float(pnl),
                        "regime": regime,
                        "exit_reason": meta.get("model_used", "ai_exit")
                    })
                    in_position = False
                    position_type = None
                    entry_price = 0.0
                continue

            if action == 1:
                in_position = True
                position_type = 'long'
                entry_price = close
            elif action == -1:
                in_position = True
                position_type = 'short'
                entry_price = close

        return trades

    def _fallback_action(self, df: pd.DataFrame, i: int, regime: int) -> Tuple[int, Dict[str, Any]]:
        """Simple but effective fallback using real features."""
        rsi = df['RSI'].iloc[i] if 'RSI' in df.columns else 50.0
        roc = df['roc'].iloc[i] if 'roc' in df.columns else 0.0

        if regime in [1, 2] and rsi > 55 and roc > 0:
            return 1, {"model_used": "fallback", "reason": "trend_entry"}
        elif regime == 0 and rsi < 35:
            return 1, {"model_used": "fallback", "reason": "mean_rev"}
        elif regime == 0 and rsi > 65:
            return -1, {"model_used": "fallback", "reason": "overbought_short"}
        else:
            return 0, {"model_used": "fallback", "reason": "hold"}

    def apply_execution_realism(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        realistic_trades = []
        for trade in trades:
            slippage = np.random.normal(0, 0.0005) if self.slippage_model == "volume_based" else 0.0
            trade["entry_price"] = float(trade["entry_price"] * (1 + slippage))
            trade["exit_price"] = float(trade["exit_price"] * (1 + slippage))
            
            pip_value = self._get_pip_value(trade['symbol'])
            raw_pnl = trade["exit_price"] - trade["entry_price"]
            trade["pnl"] = float(raw_pnl / pip_value)
            trade["pnl"] *= (1 - (self.execution_latency_ms / 1000.0) * 0.0001)
            realistic_trades.append(trade)
        return realistic_trades

    def execute_full_backtest_on_features(self, df_with_features: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        if 'regime' not in df_with_features.columns:
            df_with_features = df_with_features.copy()
            df_with_features['regime'] = np.random.choice([0, 1, 2], size=len(df_with_features))
        
        simulated_trades = self._simulate_strategy_trades(df_with_features, symbol, timeframe)
        if not simulated_trades:
            logger.warning(f"No trades generated for {symbol} {timeframe}")
            return self._empty_result(symbol)
        
        realistic_trades = self.apply_execution_realism(simulated_trades)
        pnl_values = [t["pnl"] for t in realistic_trades if "pnl" in t and not pd.isna(t["pnl"])]
        mean_pnl = float(np.mean(pnl_values)) if pnl_values else 0.0
        sharpe_ratio = 0.0
        win_rate = 0.0
        if len(pnl_values) > 1:
            std_pnl = np.std(pnl_values)
            if std_pnl > 1e-8:
                sharpe_ratio = float((np.mean(pnl_values) / std_pnl) * np.sqrt(252))
            win_rate = float(np.mean([pnl > 0 for pnl in pnl_values]))
        
        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "total_trades": len(realistic_trades),
            "mean_pnl": mean_pnl,
            "sharpe_ratio": sharpe_ratio,
            "win_rate": win_rate,
            "brier_score": 0.3,
            "calibration_pass": False,
            "regime_analysis": {},
            "statistical_significance": {"p_value": 0.5, "significant": False},
            "execution_realism_applied": True,
            "timestamp": datetime.now().isoformat()
        }
        
        result_path = os.path.join(
            "validation_lab", 
            "results", 
            f"backtest_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(result_path, "w") as f:
            import json
            json.dump(result, f, indent=2, default=str)
        logger.info(f"✅ Backtest completed for {symbol} {timeframe}. Results saved to: {result_path}")
        return result

    def _empty_result(self, symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "total_trades": 0,
            "mean_pnl": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.0,
            "brier_score": 1.0,
            "calibration_pass": False,
            "regime_analysis": {},
            "statistical_significance": {"p_value": 1.0, "significant": False},
            "execution_realism_applied": True,
            "timestamp": datetime.now().isoformat()
        }
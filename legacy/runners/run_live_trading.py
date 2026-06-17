# runners/run_live_trading.py
import os
import sys
import asyncio
import yaml
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Core system components
from core.circuit_breaker import CircuitBreaker
from intelligence.multi_agent_brain import MultiAgentBrain
from intelligence.regime_detector import RegimeDetector
from risk_fortress.neural_risk_manager import NeuralRiskManager
from risk_fortress.preemptive_guardian import PreemptiveGuardian
from execution_hub.smart_executor import SmartExecutor
from execution_hub.performance_tracker import PerformanceTracker
from validation_lab.live_paper_gateway import LivePaperGateway

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("🚀 Initiating Live Trading System")
    
    # 🔹 Load dynamic configuration
    config_path = "config/base_config.yaml"
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ Config file not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    print("✅ Configuration loaded dynamically")

    # 🔹 Verify MT5 is enabled for live trading
    if not config.get("system", {}).get("mt5", {}).get("enabled", False):
        raise RuntimeError("❌ MT5 must be enabled for live trading")
    
    # 🔹 Validate deployment certification (mandatory gate)
    gateway = LivePaperGateway(config=config)
    if not gateway.validate_deployment_certification():
        raise RuntimeError("❌ Deployment certification missing or expired. Complete paper trading first.")
    print("✅ Deployment certification validated")

    # 🔹 Initialize core components
    circuit_breaker = CircuitBreaker(config=config)
    brain = MultiAgentBrain(config=config)
    regime_detector = RegimeDetector(config=config)
    risk_manager = NeuralRiskManager(config=config)
    guardian = PreemptiveGuardian(config=config)
    executor = SmartExecutor(config=config)
    performance_tracker = PerformanceTracker(config=config)
    
    print("✅ Core components initialized")

    # 🔹 Main trading loop
    symbols = config["system"]["symbols"]
    timeframes = config["system"]["timeframes"]
    
    for symbol in symbols:
        print(f"📊 Starting live trading for {symbol}")
        
        while True:
            try:
                # 🔹 Check system health (circuit breaker)
                health_status = circuit_breaker.monitor_system_health()
                if not health_status.get("healthy", True):
                    logger.critical("🛑 Emergency stop triggered by circuit breaker")
                    circuit_breaker.trigger_emergency_stop()
                    break
                
                # 🔹 Load latest market data
                data_path = os.path.join("data_engine", "clean", f"{symbol}_H1.parquet")
                if not os.path.exists(data_path):
                    logger.warning(f"⚠️ No recent data for {symbol}. Skipping cycle.")
                    asyncio.sleep(60)
                    continue
                
                df = pd.read_parquet(data_path)
                if df.empty:
                    asyncio.sleep(60)
                    continue
                
                current_price = float(df['close'].iloc[-1])
                returns = df['close'].pct_change().dropna().values
                
                # 🔹 Detect market regime
                regime = regime_detector.detect_regime_hmm(returns)[-1]
                volatility = np.std(returns[-20:]) if len(returns) >= 20 else 0.02
                
                # 🔹 Detect unusual moves
                unusual_move = guardian.detect_unusual_moves(returns)
                
                # 🔹 Generate agent signals (simplified for live execution)
                trend_signal = 0.8 if regime == 2 else -0.3  # Trending vs mean-reverting
                trend_conf = 0.85
                risk_signal = 0.0
                risk_conf = 0.9
                volatility_signal = volatility
                volatility_conf = 0.75
                
                # 🔹 Coordinate agents
                consensus_signal, agent_weights = brain.coordinate_agents(
                    trend_signal=trend_signal,
                    trend_conf=trend_conf,
                    sentiment_signal=0.0,
                    sentiment_conf=0.5,
                    risk_signal=risk_signal,
                    risk_conf=risk_conf,
                    execution_signal=0.0,
                    execution_conf=0.5,
                    volatility_signal=volatility_signal,
                    volatility_conf=volatility_conf
                )
                
                # 🔹 Check for early exit conditions
                agent_confidences = {
                    "trend": trend_conf,
                    "risk": risk_conf,
                    "volatility": volatility_conf
                }
                win_rate = performance_tracker.get_current_win_rate(symbol)
                should_exit, exit_reason = brain.should_trigger_early_exit(
                    agent_confidences, win_rate, unusual_move
                )
                
                if should_exit:
                    # 🔹 Execute early exit
                    positions = executor.get_open_positions(symbol)
                    for pos in positions:
                        executor.execute_early_exit(
                            symbol=symbol,
                            ticket=pos["ticket"],
                            position_size=pos["volume"],
                            reason=exit_reason
                        )
                    continue
                
                # 🔹 Determine action
                if consensus_signal > 0.5:
                    action = 1  # Buy
                elif consensus_signal < -0.5:
                    action = 3  # Sell
                else:
                    action = 2  # Hold
                
                if action == 2:
                    asyncio.sleep(60)
                    continue
                
                # 🔹 Calculate position size
                equity = performance_tracker.get_current_equity()
                stop_loss_pips = 100  # This would come from dynamic ATR calculation
                position_size = risk_manager.calculate_position_size(
                    equity=equity,
                    stop_loss_pips=stop_loss_pips,
                    symbol=symbol
                )
                
                if position_size <= 0:
                    logger.warning("⚠️ Position size <= 0. Skipping trade.")
                    asyncio.sleep(60)
                    continue
                
                # 🔹 Apply preemptive derisking
                health_score = guardian.assess_strategy_health(agent_confidences, volatility)
                position_size = guardian.implement_preemptive_derisking(position_size, health_score)
                
                # 🔹 Calculate stop loss and take profit
                profile = config["risk_profiles"][f"{symbol}_risk_profile"]
                pip_value = profile["pip_value_per_lot"]
                min_stop_pips = profile["min_stop_pips"]
                sl_price = current_price - (min_stop_pips * pip_value) if action == 1 else current_price + (min_stop_pips * pip_value)
                tp_price = current_price + (200 * pip_value) if action == 1 else current_price - (200 * pip_value)
                
                # 🔹 Execute trade
                result = executor.execute_trade(
                    symbol=symbol,
                    action=action,
                    position_size=position_size,
                    stop_loss=sl_price,
                    take_profit=tp_price
                )
                
                if result["status"] == "success":
                    logger.info(f"✅ Trade executed: {symbol} {action} {position_size:.2f} lots")
                    # 🔹 Start trailing stop monitoring in background
                    asyncio.create_task(
                        monitor_trailing_stop(
                            executor, guardian, symbol, result["ticket"], 
                            current_price, sl_price, regime
                        )
                    )
                
                # 🔹 Update performance tracker
                performance_tracker.log_trade(result, symbol, consensus_signal, agent_weights)
                
                # 🔹 Sleep before next cycle
                asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ Error in trading loop for {symbol}: {e}")
                # Log to config_errors.log
                error_log_path = os.path.join("logs", "config_errors.log")
                os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
                with open(error_log_path, "a") as f:
                    f.write(f"[{datetime.now().isoformat()}] [run_live_trading] [Critical] {str(e)} [Unresolved]\n")
                
                # Check if circuit breaker should trigger
                circuit_breaker.handle_component_failure("trading_loop", str(e))
                asyncio.sleep(60)

async def monitor_trailing_stop(executor, guardian, symbol, ticket, entry_price, base_stop, regime):
    """Background task to monitor and update trailing stops."""
    while True:
        try:
            # Get current price
            data_path = os.path.join("data_engine", "clean", f"{symbol}_H1.parquet")
            if os.path.exists(data_path):
                df = pd.read_parquet(data_path)
                if not df.empty:
                    current_price = float(df['close'].iloc[-1])
                    
                    # Update trailing stop
                    success = executor.manage_trailing_stop(
                        symbol=symbol,
                        ticket=ticket,
                        entry_price=entry_price,
                        current_price=current_price,
                        base_stop=base_stop,
                        regime=regime
                    )
                    
                    if success:
                        logger.info(f"🔄 Trailing stop updated for {symbol} ticket {ticket}")
            
            await asyncio.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            logger.warning(f"⚠️ Trailing stop monitor error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    print("🎯 Live Trading System Starting...")
    print("⚠️  WARNING: REAL CAPITAL AT RISK")
    print("🔒 Circuit breaker and risk controls active")
    main()
    print("📂 Live trading logs stored in: ./logs/")
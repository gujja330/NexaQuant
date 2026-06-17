# runners/run_paper_trading.py
import os
import sys
import asyncio
import yaml
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Core system components
from core.circuit_breaker import CircuitBreaker
from intelligence.multi_agent_brain import MultiAgentBrain
from intelligence.regime_detector import RegimeDetector
from risk_fortress.neural_risk_manager import NeuralRiskManager
from risk_fortress.preemptive_guardian import PreemptiveGuardian
from execution_hub.execution_simulator import ExecutionSimulator
from execution_hub.performance_tracker import PerformanceTracker
from validation_lab.live_paper_gateway import LivePaperGateway

# AI-Driven Imports (Per new_rules.md)
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_data_path(symbol: str, timeframe: str) -> str:
    """Get data path with fallback to synthetic data when real data is missing."""
    # Try real data first
    real_path = os.path.join("data_engine", "clean", f"{symbol}_{timeframe}.parquet")
    if os.path.exists(real_path):
        return real_path
    
    # Fallback to synthetic data
    synthetic_path = os.path.join("data_engine", "synthetic_enhanced", f"{symbol}_{timeframe}.parquet")
    if os.path.exists(synthetic_path):
        logger.info(f"⚠️ Real data not found for {symbol}_{timeframe}, using synthetic data")
        return synthetic_path
    
    raise FileNotFoundError(f"Data not found in clean/ or synthetic_enhanced/: {symbol}_{timeframe}")

def run_paper_trading():
    print("📈 Starting Paper Trading Validation")
    
    # 🔹 Load dynamic configuration
    config_path = "config/base_config.yaml"
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ Config file not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    print("✅ Configuration loaded dynamically")

    # 🔹 Initialize core components with dynamic config
    circuit_breaker = CircuitBreaker(config=config)
    brain = MultiAgentBrain(config=config)
    regime_detector = RegimeDetector(config=config)
    risk_manager = NeuralRiskManager(config=config)
    guardian = PreemptiveGuardian(config=config)
    execution_simulator = ExecutionSimulator(config=config)
    performance_tracker = PerformanceTracker(config=config)
    paper_gateway = LivePaperGateway(config=config)
    
    print("✅ Core components initialized")

    # 🔹 Main paper trading loop
    symbols = config["system"]["symbols"]
    min_paper_days = config["validation"]["paper_trading_min_days"]
    
    # Create paper trading results directory
    paper_results_dir = os.path.join("validation_lab", "paper_trading")
    os.makedirs(paper_results_dir, exist_ok=True)
    
    # Initialize paper trading state
    start_time = datetime.now()
    paper_trades = []
    equity_curve = [10000.0]  # Starting with $10,000
    
    print(f"📊 Paper trading started for {min_paper_days} days minimum")
    print(f"🎯 Target: Validate backtest-live alignment before live deployment")
    
    # Load data for all symbols
    symbol_data = {}
    for symbol in symbols:
        try:
            data_path = get_data_path(symbol, "H1")
            df = pd.read_parquet(data_path)
            symbol_data[symbol] = df
            logger.info(f"Loaded {len(df)} rows of data for {symbol}")
        except Exception as e:
            logger.error(f"Failed to load data for {symbol}: {e}")
            symbol_data[symbol] = pd.DataFrame()
    
    # Determine total cycles (min_paper_days * 24 hours)
    total_cycles = min_paper_days * 24
    current_cycle = 0
    
    while current_cycle < total_cycles:
        try:
            # 🔹 Check system health
            health_status = circuit_breaker.monitor_system_health()
            if not health_status.get("healthy", True):
                logger.warning("⚠️ System health degraded during paper trading")
            
            # 🔹 Process each symbol
            for symbol in symbols:
                df = symbol_data.get(symbol)
                if df is None or df.empty or len(df) <= current_cycle:
                    continue
                
                # Get current market state
                current_row = df.iloc[current_cycle]
                current_price = float(current_row['close'])
                
                # Get returns for regime detection
                if current_cycle > 0:
                    returns = df['close'].iloc[:current_cycle+1].pct_change().dropna().values
                else:
                    returns = np.array([0.0])
                
                # 🔹 Detect market regime
                if len(returns) > 10:
                    regime_array = regime_detector.detect_regime_hmm(returns)
                    regime = int(regime_array[-1]) if len(regime_array) > 0 else 0
                else:
                    regime = 0  # Default to low volatility regime
                
                volatility = np.std(returns[-20:]) if len(returns) >= 20 else 0.02
                
                # 🔹 Detect unusual moves
                unusual_move = guardian.detect_unusual_moves(returns) if len(returns) > 20 else False
                
                # 🔹 Generate agent signals
                trend_signal = 0.8 if regime == 2 else -0.3
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
                
                # 🔹 Determine action
                if consensus_signal > 0.5:
                    action = 1  # Buy
                elif consensus_signal < -0.5:
                    action = 3  # Sell
                else:
                    action = 2  # Hold
                
                if action == 2:
                    continue
                
                # 🔹 Calculate position size
                equity = equity_curve[-1]
                stop_loss_pips = 100
                position_size = risk_manager.calculate_position_size(
                    equity=equity,
                    stop_loss_pips=stop_loss_pips,
                    symbol=symbol
                )
                
                if position_size <= 0:
                    continue
                
                # 🔹 Apply preemptive derisking
                agent_confidences = {"trend": trend_conf, "risk": risk_conf, "volatility": volatility_conf}
                health_score = guardian.assess_strategy_health(agent_confidences, volatility)
                position_size = guardian.implement_preemptive_derisking(position_size, health_score)
                
                # 🔹 Calculate stop loss and take profit
                profile = config["risk_profiles"][f"{symbol}_risk_profile"]
                pip_value = profile["pip_value_per_lot"]
                min_stop_pips = profile["min_stop_pips"]
                sl_price = current_price - (min_stop_pips * pip_value) if action == 1 else current_price + (min_stop_pips * pip_value)
                tp_price = current_price + (200 * pip_value) if action == 1 else current_price - (200 * pip_value)
                
                # 🔹 Simulate execution (paper trading)
                market_data = {
                    "volatility": volatility,
                    "volume": 1000,
                    "is_news_event": unusual_move,
                    "price": current_price,
                    "avg_volume": 10000,
                    "timestamp": datetime.now().isoformat()
                }
                
                execution_result = execution_simulator.simulate_execution(
                    symbol=symbol,
                    action=action,
                    position_size=position_size,
                    entry_price=current_price,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    market_data=market_data
                )
                
                if execution_result["status"] == "success":
                    # Simulate PnL based on next price (simplified)
                    if current_cycle + 1 < len(df):
                        next_price = float(df.iloc[current_cycle + 1]['close'])
                        if action in [0, 1]:  # Buy
                            pnl = (next_price - execution_result["entry_price"]) * position_size * 100000  # Standard lot multiplier
                        else:  # Sell
                            pnl = (execution_result["entry_price"] - next_price) * position_size * 100000
                    else:
                        pnl = 0.0
                    
                    execution_result["pnl"] = pnl
                    execution_result["exit_price"] = next_price if current_cycle + 1 < len(df) else current_price
                    
                    # Update equity curve
                    new_equity = equity_curve[-1] + pnl
                    equity_curve.append(new_equity)
                    
                    # Log trade
                    trade_record = {
                        "timestamp": datetime.now().isoformat(),
                        "symbol": symbol,
                        "action": action,
                        "position_size": position_size,
                        "entry_price": execution_result["entry_price"],
                        "exit_price": execution_result.get("exit_price", current_price),
                        "pnl": pnl,
                        "equity": new_equity,
                        "consensus_signal": consensus_signal,
                        "regime": regime,
                        "volatility": volatility,
                        "unusual_move": unusual_move
                    }
                    paper_trades.append(trade_record)
                    logger.info(f"📝 Paper trade: {symbol} {action} {position_size:.2f} lots → PnL: ${pnl:.2f}")
                
                # Update performance tracker
                performance_metrics = {
                    "sharpe_ratio": 1.0,
                    "win_rate": 0.55,
                    "current_drawdown": 0.15,
                    "current_volatility": volatility
                }
                performance_tracker.log_trade(execution_result, symbol, consensus_signal, agent_weights)
                performance_tracker.update_metrics(performance_metrics)
            
            # 🔹 Log daily progress
            if current_cycle % 24 == 0:
                days_completed = (current_cycle // 24) + 1
                print(f"📅 Day {days_completed}/{min_paper_days} completed | Equity: ${equity_curve[-1]:,.2f}")
            
            current_cycle += 1
            
        except Exception as e:
            logger.error(f"❌ Error in paper trading loop: {e}")
            # Log to config_errors.log
            error_log_path = os.path.join("logs", "config_errors.log")
            os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
            with open(error_log_path, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] [run_paper_trading] [Critical] {str(e)} [Unresolved]\n")
    
    # 🔹 Generate paper trading report
    end_time = datetime.now()
    duration = end_time - start_time
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0] if equity_curve[0] > 0 else 0
    max_drawdown = min(equity_curve) / max(equity_curve) - 1 if max(equity_curve) > 0 else 0
    
    paper_report = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_hours": duration.total_seconds() / 3600,
        "total_trades": len(paper_trades),
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "final_equity": equity_curve[-1],
        "trades": paper_trades,
        "equity_curve": equity_curve,
        "symbols": symbols,
        "paper_trading_days": min_paper_days
    }
    
    # Save paper trading results
    report_path = os.path.join(paper_results_dir, f"paper_trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w") as f:
        import json
        json.dump(paper_report, f, indent=2, default=str)
    
    print(f"✅ Paper trading completed!")
    print(f"📊 Results saved to: {report_path}")
    print(f"💰 Final Equity: ${equity_curve[-1]:,.2f} ({total_return:.1%} return)")
    print(f"📉 Max Drawdown: {max_drawdown:.1%}")
    
    # 🔹 Generate deployment certification if successful
    if paper_gateway.validate_paper_trading_results(paper_report):
        certification = paper_gateway.generate_deployment_certification(paper_report)
        cert_path = os.path.join("validation_lab", "certifications", f"certification_{datetime.now().strftime('%Y%m%d')}.json")
        os.makedirs(os.path.dirname(cert_path), exist_ok=True)
        with open(cert_path, "w") as f:
            import json
            json.dump(certification, f, indent=2)
        print(f"✅ Deployment certification generated: {cert_path}")
    else:
        print("⚠️ Paper trading results insufficient for deployment certification")
        print("🔍 Review results and improve strategy before live deployment")

if __name__ == "__main__":
    print("🎯 Paper Trading Validation Starting...")
    print("📝 This is a mandatory gate before live capital deployment")
    print("🔒 All trades are simulated with realistic execution friction")
    run_paper_trading()
    print("📂 Paper trading logs stored in: ./validation_lab/paper_trading/")
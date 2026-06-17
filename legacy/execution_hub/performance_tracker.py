import os
import yaml
import numpy as np
import pandas as pd
from typing import Dict, Any
from sklearn.ensemble import IsolationForest
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceTracker:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Continuous performance monitoring with AI-driven pattern recognition and anomaly detection.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.performance_data = []
        self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def track_real_time_metrics(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Live calculation of key performance indicators."""
        self.performance_data.append(trade_data)
        
        # Calculate metrics
        df = pd.DataFrame(self.performance_data)
        if len(df) < 2:
            return {"status": "insufficient_data"}
        
        # PnL calculation
        pnl = df['pnl'].sum() if 'pnl' in df.columns else 0
        
        # Win rate
        wins = len(df[df['pnl'] > 0]) if 'pnl' in df.columns else 0
        total_trades = len(df)
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        # Sharpe ratio (simplified)
        if 'pnl' in df.columns and len(df) > 1:
            returns = df['pnl'].pct_change().dropna()
            if len(returns) > 1 and returns.std() > 0:
                sharpe = returns.mean() / returns.std() * np.sqrt(252)
            else:
                sharpe = 0
        else:
            sharpe = 0
        
        # Maximum drawdown
        if 'equity' in df.columns:
            equity = df['equity']
            peak = equity.cummax()
            drawdown = (peak - equity) / peak
            max_drawdown = drawdown.max()
        else:
            max_drawdown = 0
        
        metrics = {
            "total_pnl": float(pnl),
            "win_rate": float(win_rate),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "total_trades": int(total_trades),
            "current_equity": float(df['equity'].iloc[-1]) if 'equity' in df.columns else 0
        }
        
        logger.info(f"Performance metrics: {metrics}")
        return metrics

    def detect_performance_drift(self, metrics_history: pd.DataFrame) -> Dict[str, Any]:
        """Statistical drift detection enhanced with isolation forest anomaly detection."""
        if len(metrics_history) < 10:
            return {"drift_detected": False, "anomalies": []}
        
        # Prepare features for anomaly detection
        features = metrics_history[['win_rate', 'sharpe_ratio', 'max_drawdown']].fillna(0)
        
        # Fit and predict anomalies
        self.anomaly_detector.fit(features)
        anomaly_scores = self.anomaly_detector.decision_function(features)
        anomalies = self.anomaly_detector.predict(features)
        
        # Check for recent anomalies
        recent_anomalies = anomalies[-5:]  # Last 5 periods
        drift_detected = np.any(recent_anomalies == -1)
        
        return {
            "drift_detected": bool(drift_detected),
            "anomaly_scores": anomaly_scores.tolist(),
            "anomalies": anomalies.tolist(),
            "recent_anomaly_count": int(np.sum(recent_anomalies == -1))
        }

    def analyze_attribution(self, agent_contributions: Dict[str, float], trade_pnl: float) -> Dict[str, float]:
        """Factor-based attribution analysis with agent-specific performance breakdown."""
        total_contribution = sum(agent_contributions.values())
        if total_contribution == 0:
            return {agent: 0.0 for agent in agent_contributions}
        
        attribution = {}
        for agent, contribution in agent_contributions.items():
            attribution[agent] = float((contribution / total_contribution) * trade_pnl)
        
        return attribution

    def monitor_agent_anomalies(self, agent_performance: Dict[str, Any]) -> Dict[str, bool]:
        """Real-time anomaly detection for individual agent performance degradation."""
        anomalies = {}
        for agent, metrics in agent_performance.items():
            # Simple threshold-based anomaly detection
            if isinstance(metrics, dict):
                win_rate = metrics.get("win_rate", 0.5)
                confidence = metrics.get("confidence", 0.8)
                
                # Flag if win rate drops below 40% or confidence below 60%
                anomalies[agent] = win_rate < 0.4 or confidence < 0.6
            else:
                anomalies[agent] = False
        
        return anomalies

    def generate_intelligent_alerts(self, performance_metrics: Dict[str, Any], drift_results: Dict[str, Any]) -> List[str]:
        """Context-aware alert generation with multi-agent drift notifications."""
        alerts = []
        
        # Performance-based alerts
        if performance_metrics.get("win_rate", 0.5) < 0.45:
            alerts.append("⚠️ Win rate below 45% - investigate agent performance")
        
        if performance_metrics.get("sharpe_ratio", 1.0) < 0.8:
            alerts.append("⚠️ Sharpe ratio below 0.8 - increase risk management")
        
        if performance_metrics.get("max_drawdown", 0.1) > 0.2:
            alerts.append("🚨 Maximum drawdown exceeds 20% - reduce position sizes")
        
        # Drift-based alerts
        if drift_results.get("drift_detected", False):
            alerts.append("🔍 Performance drift detected - consider model retraining")
        
        if drift_results.get("recent_anomaly_count", 0) > 2:
            alerts.append("🚨 Multiple anomalies detected - check data quality and market regime")
        
        return alerts
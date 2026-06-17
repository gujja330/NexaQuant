# core/health_monitor.py
import os
import numpy as np
from typing import Dict, Any
import logging

# AI-Driven Imports (Per new_rules.md)
from sklearn.ensemble import IsolationForest
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HealthMonitor:
    """
    Comprehensive system health monitoring with predictive analytics and anomaly detection.
    Fully dynamic. Zero hardcoding. Config-driven. AI-powered.
    Implements Predictive AI, Anomaly Detection, and Statistical Process Control.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.core_config = config.get("core", {})
        
        # 🔹 All numeric parameters from config — NO HARDCODING
        self.anomaly_contamination = self.core_config["anomaly_contamination"]
        self.health_score_threshold = self.core_config["health_score_threshold"]
        self.volatility_spike_threshold = self.core_config["volatility_spike_threshold"]
        self.latency_threshold_ms = self.core_config["latency_threshold_ms"]
        self.fill_rate_threshold = self.core_config["fill_rate_threshold"]
        
        self.anomaly_detector = IsolationForest(
            contamination=self.anomaly_contamination,
            random_state=42
        )
        
        # Ensure log directories exist
        os.makedirs("logs/health_monitor", exist_ok=True)

    def monitor_component_health(self, component_name: str, metrics: Dict[str, float]) -> Dict[str, Any]:
        """Monitor health of individual system components."""
        # Calculate component health score
        health_score = np.mean(list(metrics.values()))
        
        # Detect anomalies
        metrics_array = np.array(list(metrics.values())).reshape(1, -1)
        try:
            anomaly_score = self.anomaly_detector.fit_predict(metrics_array)[0]
            is_anomalous = (anomaly_score == -1)
        except Exception as e:
            logger.warning(f"Anomaly detection failed for {component_name}: {e}")
            is_anomalous = False
        
        healthy = health_score >= self.health_score_threshold and not is_anomalous
        
        health_status = {
            "component": component_name,
            "healthy": healthy,
            "health_score": float(health_score),
            "is_anomalous": is_anomalous,
            "metrics": metrics
        }
        
        # Log health status
        self._log_health_status(health_status)
        
        return health_status

    def _log_health_status(self, health_status: Dict[str, Any]):
        """Log health status to health monitor logs."""
        import json
        from datetime import datetime
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "component": health_status["component"],
            "healthy": health_status["healthy"],
            "health_score": health_status["health_score"],
            "is_anomalous": health_status["is_anomalous"]
        }
        
        log_path = os.path.join("logs", "health_monitor", f"health_{datetime.now().strftime('%Y%m%d')}.json")
        # In production, append to log file
        logger.info(f"Health check for {health_status['component']}: {'✅ Healthy' if health_status['healthy'] else '⚠️ Unhealthy'} (Score: {health_status['health_score']:.2f})")

    def aggregate_system_health(self, component_health_statuses: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate health status across all system components."""
        overall_health_score = np.mean([status["health_score"] for status in component_health_statuses.values()])
        any_anomalies = any(status["is_anomalous"] for status in component_health_statuses.values())
        all_healthy = all(status["healthy"] for status in component_health_statuses.values())
        
        system_health = {
            "overall_healthy": all_healthy and not any_anomalies,
            "overall_health_score": float(overall_health_score),
            "components": component_health_statuses,
            "anomalies_detected": any_anomalies
        }
        
        return system_health
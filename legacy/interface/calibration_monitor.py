import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CalibrationMonitor:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Real-time monitoring of model prediction calibration with reliability assessment and confidence tracking.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./interface/calibration_dashboards/"
        os.makedirs(self.output_dir, exist_ok=True)
        self.brier_threshold = self.config.get("validation", {}).get("brier_score_threshold", 0.25)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def calculate_calibration_metrics(self, predictions: np.ndarray, actuals: np.ndarray, confidences: np.ndarray) -> Dict[str, float]:
        """
        Calculate comprehensive calibration metrics including Brier score and reliability error.
        """
        if len(predictions) == 0 or len(actuals) == 0 or len(confidences) == 0:
            return {"brier_score": 1.0, "reliability_error": 1.0, "calibration_status": "INSUFFICIENT_DATA"}
        
        # Calculate Brier score
        brier_score = brier_score_loss(actuals, predictions)
        
        # Calculate reliability error using calibration curve
        try:
            fraction_of_positives, mean_predicted_value = calibration_curve(actuals, confidences, n_bins=10)
            reliability_error = np.mean(np.abs(fraction_of_positives - mean_predicted_value))
        except Exception as e:
            logger.warning(f"Calibration curve failed: {e}")
            reliability_error = 1.0
        
        # Determine calibration status
        calibration_status = "CALIBRATED" if brier_score <= self.brier_threshold else "MIS_CALIBRATED"
        
        return {
            "brier_score": float(brier_score),
            "reliability_error": float(reliability_error),
            "calibration_status": calibration_status,
            "threshold": self.brier_threshold
        }

    def generate_calibration_alerts(self, calibration_metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        Generate automated alerts when calibration degrades beyond thresholds.
        """
        brier_score = calibration_metrics.get("brier_score", 1.0)
        threshold = calibration_metrics.get("threshold", 0.25)
        
        alerts = {
            "calibration_alert": brier_score > threshold,
            "severity": "HIGH" if brier_score > threshold * 1.5 else "MEDIUM" if brier_score > threshold else "LOW",
            "message": f"Brier score {brier_score:.4f} exceeds threshold {threshold:.4f}",
            "recommended_action": "RETRAIN_MODEL" if brier_score > threshold else "MONITOR"
        }
        
        if alerts["calibration_alert"]:
            logger.warning(f"Calibration alert: {alerts['message']}")
        
        return alerts

    def visualize_prediction_reliability(self, predictions: np.ndarray, actuals: np.ndarray, confidences: np.ndarray, symbol: str = "ALL") -> str:
        """
        Create interactive reliability diagram with confidence vs accuracy alignment.
        """
        if len(predictions) == 0:
            logger.warning("No data for reliability visualization")
            return ""
        
        # Create reliability curve
        try:
            fraction_of_positives, mean_predicted_value = calibration_curve(actuals, confidences, n_bins=10)
        except Exception as e:
            logger.warning(f"Calibration curve failed for visualization: {e}")
            fraction_of_positives = mean_predicted_value = np.array([0.5])
        
        # Create subplot
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                f"Reliability Diagram - {symbol}",
                f"Confidence vs Accuracy - {symbol}",
                f"Brier Score Trend - {symbol}",
                f"Prediction Distribution - {symbol}"
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        # Reliability diagram
        fig.add_trace(
            go.Scatter(x=mean_predicted_value, y=fraction_of_positives, 
                      mode='markers+lines', name='Model Calibration',
                      marker=dict(size=8)),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=[0, 1], y=[0, 1], mode='lines', 
                      name='Perfect Calibration', line=dict(dash='dash')),
            row=1, col=1
        )
        
        # Confidence vs accuracy scatter
        fig.add_trace(
            go.Scatter(x=confidences, y=actuals, mode='markers', 
                      name='Predictions', opacity=0.6),
            row=1, col=2
        )
        
        # Brier score trend (simplified)
        brier_scores = [brier_score_loss(actuals[:i], predictions[:i]) for i in range(10, len(predictions), max(1, len(predictions)//20))]
        fig.add_trace(
            go.Scatter(y=brier_scores, mode='lines+markers', name='Brier Score'),
            row=2, col=1
        )
        
        # Prediction distribution
        fig.add_trace(
            go.Histogram(x=predictions, nbinsx=20, name='Predictions'),
            row=2, col=2
        )
        
        # Update layout
        fig.update_layout(
            title=f"Calibration Monitoring Dashboard - {symbol}",
            height=800,
            showlegend=True
        )
        
        # Save dashboard
        dashboard_path = os.path.join(self.output_dir, f"calibration_dashboard_{symbol}.html")
        fig.write_html(dashboard_path)
        logger.info(f"Calibration dashboard saved: {dashboard_path}")
        return dashboard_path

    def monitor_confidence_accuracy_alignment(self, symbol: str, predictions: np.ndarray, actuals: np.ndarray, confidences: np.ndarray) -> Dict[str, Any]:
        """
        Track prediction confidence vs actual accuracy alignment with statistical testing.
        """
        if len(predictions) < 10:
            return {"alignment_valid": False, "correlation": 0.0, "p_value": 1.0}
        
        # Calculate correlation between confidence and accuracy
        from scipy.stats import pearsonr
        correlation, p_value = pearsonr(confidences, actuals)
        
        # Check if correlation is statistically significant and positive
        alignment_valid = correlation > 0.3 and p_value < 0.05
        
        return {
            "alignment_valid": bool(alignment_valid),
            "correlation": float(correlation),
            "p_value": float(p_value),
            "confidence_mean": float(np.mean(confidences)),
            "accuracy_mean": float(np.mean(actuals))
        }

    def generate_calibration_report(self, symbol: str, calibration_metrics: Dict[str, float], alerts: Dict[str, Any]) -> str:
        """
        Generate comprehensive calibration monitoring report with actionable insights.
        """
        report = {
            "report_id": f"CALIB_REPORT_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            "symbol": symbol,
            "timestamp": pd.Timestamp.now().isoformat(),
            "calibration_metrics": calibration_metrics,
            "alerts": alerts,
            "status": "APPROVED" if not alerts.get("calibration_alert", False) else "REQUIRES_ATTENTION",
            "recommendation": "PROCEED" if not alerts.get("calibration_alert", False) else "RETRAIN_MODEL"
        }
        
        # Save report
        report_path = os.path.join(self.output_dir, f"calibration_report_{symbol}_{report['report_id']}.json")
        import json
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Calibration report generated: {report_path}")
        return report_path
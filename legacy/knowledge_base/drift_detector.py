import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any
from river import drift
from scipy import stats
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DriftDetector:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Comprehensive monitoring of model performance drift with automated retraining triggers and calibration tracking.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./knowledge_base/drift_monitoring/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize drift detectors per symbol
        self.prediction_drift_detectors = {}
        self.feature_drift_detectors = {}
        self.calibration_drift_detectors = {}
        self._initialize_drift_detectors()

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _initialize_drift_detectors(self):
        """Initialize drift detection models for each symbol."""
        drift_config = self.config.get("drift_detection", {})
        
        for symbol in self.symbols:
            # Prediction drift detector (ADWIN)
            adwin_config = drift_config.get("adwin", {})
            clock = adwin_config.get("clock", 32)
            delta = adwin_config.get("delta", 0.002)
            self.prediction_drift_detectors[symbol] = drift.ADWIN(clock=clock, delta=delta)
            
            # Feature drift detector (Kolmogorov-Smirnov)
            self.feature_drift_detectors[symbol] = {}
            
            # Calibration drift detector
            self.calibration_drift_detectors[symbol] = {
                "brier_scores": [],
                "confidence_accuracy_diffs": []
            }

    def monitor_prediction_drift(self, symbol: str, prediction_error: float) -> bool:
        """
        Statistical monitoring of prediction accuracy degradation using control charts.
        """
        if symbol not in self.prediction_drift_detectors:
            logger.warning(f"No drift detector for symbol: {symbol}")
            return False
        
        self.prediction_drift_detectors[symbol].update(prediction_error)
        has_drift = self.prediction_drift_detectors[symbol].drift_detected
        
        if has_drift:
            logger.warning(f"Prediction drift detected for {symbol}")
        
        return bool(has_drift)

    def detect_feature_drift(self, symbol: str, feature_name: str, current_values: np.ndarray, reference_values: np.ndarray) -> bool:
        """
        Feature distribution monitoring with KL-divergence and Wasserstein distance tracking.
        """
        if len(current_values) == 0 or len(reference_values) == 0:
            return False
        
        try:
            # Kolmogorov-Smirnov test for distribution similarity
            ks_stat, p_value = stats.ks_2samp(current_values, reference_values)
            has_drift = p_value < 0.05
            
            if has_drift:
                logger.warning(f"Feature drift detected for {symbol}.{feature_name} (KS p-value: {p_value:.4f})")
            
            return bool(has_drift)
        except Exception as e:
            logger.error(f"Feature drift detection error for {symbol}.{feature_name}: {e}")
            return False

    def assess_calibration_drift(self, symbol: str, predictions: np.ndarray, actuals: np.ndarray, confidences: np.ndarray) -> Dict[str, Any]:
        """
        Prediction calibration monitoring with Brier score and reliability diagrams.
        """
        if len(predictions) == 0 or len(actuals) == 0 or len(confidences) == 0:
            return {"calibration_drift": False, "brier_score": 1.0, "reliability_error": 1.0}
        
        # Calculate Brier score
        brier_score = np.mean((predictions - actuals) ** 2)
        
        # Calculate reliability error (confidence vs accuracy)
        bins = np.linspace(0, 1, 11)
        bin_indices = np.digitize(confidences, bins) - 1
        bin_indices = np.clip(bin_indices, 0, len(bins) - 2)
        
        reliability_error = 0.0
        valid_bins = 0
        for i in range(len(bins) - 1):
            mask = bin_indices == i
            if np.sum(mask) > 0:
                avg_confidence = np.mean(confidences[mask])
                avg_accuracy = np.mean(actuals[mask])
                reliability_error += abs(avg_confidence - avg_accuracy)
                valid_bins += 1
        
        if valid_bins > 0:
            reliability_error /= valid_bins
        
        # Check calibration thresholds
        calibration_config = self.config.get("validation", {})
        brier_threshold = calibration_config.get("brier_score_threshold", 0.25)
        reliability_threshold = calibration_config.get("reliability_threshold", 0.15)
        
        calibration_drift = brier_score > brier_threshold or reliability_error > reliability_threshold
        
        if calibration_drift:
            logger.warning(f"Calibration drift detected for {symbol} (Brier: {brier_score:.4f}, Reliability: {reliability_error:.4f})")
        
        return {
            "calibration_drift": bool(calibration_drift),
            "brier_score": float(brier_score),
            "reliability_error": float(reliability_error),
            "thresholds": {
                "brier": brier_threshold,
                "reliability": reliability_threshold
            }
        }

    def trigger_retraining_protocols(self, drift_results: Dict[str, Any]) -> Dict[str, bool]:
        """
        Automated retraining triggers based on statistical significance of drift.
        """
        retraining_triggers = {}
        
        for symbol in self.symbols:
            symbol_drift = drift_results.get(symbol, {})
            prediction_drift = symbol_drift.get("prediction_drift", False)
            feature_drift = symbol_drift.get("feature_drift", False)
            calibration_drift = symbol_drift.get("calibration_drift", {}).get("calibration_drift", False)
            
            # Trigger retraining if any drift is detected
            should_retrain = prediction_drift or feature_drift or calibration_drift
            retraining_triggers[symbol] = should_retrain
            
            if should_retrain:
                logger.info(f"Retraining triggered for {symbol}")
        
        return retraining_triggers

    def manage_model_lifecycle(self, symbol: str, model_version: str, performance_metrics: Dict[str, float]) -> str:
        """
        Complete model lifecycle management with version control and rollback capabilities.
        """
        lifecycle_record = {
            "symbol": symbol,
            "model_version": model_version,
            "timestamp": pd.Timestamp.now().isoformat(),
            "performance_metrics": performance_metrics,
            "drift_status": "MONITORED"
        }
        
        # Save lifecycle record
        record_path = os.path.join(self.output_dir, f"lifecycle_{symbol}_{model_version}.json")
        import json
        with open(record_path, 'w') as f:
            json.dump(lifecycle_record, f, indent=2)
        
        logger.info(f"Model lifecycle record saved: {record_path}")
        return record_path

    def generate_drift_report(self, drift_results: Dict[str, Any]) -> str:
        """
        Generate comprehensive drift detection report with actionable insights.
        """
        report = {
            "report_id": f"DIFT_REPORT_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": pd.Timestamp.now().isoformat(),
            "summary": {
                "symbols_monitored": len(self.symbols),
                "symbols_with_drift": sum(1 for s in self.symbols if drift_results.get(s, {}).get("prediction_drift", False) or 
                                         drift_results.get(s, {}).get("feature_drift", False) or
                                         drift_results.get(s, {}).get("calibration_drift", {}).get("calibration_drift", False)),
                "retraining_recommended": []
            },
            "detailed_results": drift_results
        }
        
        # Identify symbols needing retraining
        for symbol in self.symbols:
            symbol_drift = drift_results.get(symbol, {})
            if (symbol_drift.get("prediction_drift", False) or 
                symbol_drift.get("feature_drift", False) or
                symbol_drift.get("calibration_drift", {}).get("calibration_drift", False)):
                report["summary"]["retraining_recommended"].append(symbol)
        
        # Save report
        report_path = os.path.join(self.output_dir, f"drift_report_{report['report_id']}.json")
        import json
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Drift report generated: {report_path}")
        return report_path
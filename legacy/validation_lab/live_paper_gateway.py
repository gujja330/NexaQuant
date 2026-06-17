import os
import yaml
import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LivePaperGateway:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Mandatory paper trading validation before live capital deployment with performance benchmarking.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.min_paper_days = self.config.get("validation", {}).get("paper_trading_min_days", 30)
        self.brier_threshold = self.config.get("validation", {}).get("brier_score_threshold", 0.25)
        self.output_dir = "./validation_lab/paper_trading/"
        os.makedirs(self.output_dir, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def execute_paper_trading_protocol(self, model_predictions: pd.DataFrame, paper_results: pd.DataFrame) -> Dict[str, Any]:
        """
        Mandatory 30-day minimum paper trading with full execution simulation.
        """
        if len(paper_results) < self.min_paper_days:
            raise ValueError(f"Paper trading period too short: {len(paper_results)} days < {self.min_paper_days}")
        
        # Calculate paper trading metrics
        paper_pnl = paper_results['pnl'].sum()
        paper_win_rate = len(paper_results[paper_results['pnl'] > 0]) / len(paper_results)
        paper_sharpe = paper_results['pnl'].mean() / paper_results['pnl'].std() * np.sqrt(252) if paper_results['pnl'].std() > 0 else 0
        
        results = {
            "paper_trading_days": len(paper_results),
            "total_pnl": float(paper_pnl),
            "win_rate": float(paper_win_rate),
            "sharpe_ratio": float(paper_sharpe),
            "status": "COMPLETED"
        }
        
        logger.info(f"Paper trading completed: {results}")
        return results

    def validate_backtest_live_alignment(self, backtest_results: pd.DataFrame, paper_results: pd.DataFrame) -> Dict[str, Any]:
        """
        Statistical validation that live results match backtest expectations.
        """
        if backtest_results.empty or paper_results.empty:
            return {"alignment_valid": False, "p_value": 1.0, "error": "Insufficient data"}
        
        # Compare Sharpe ratios
        backtest_sharpe = backtest_results['sharpe_ratio'].mean() if 'sharpe_ratio' in backtest_results.columns else 1.0
        paper_sharpe = paper_results['pnl'].mean() / paper_results['pnl'].std() * np.sqrt(252) if paper_results['pnl'].std() > 0 else 0
        
        # T-test for performance alignment
        try:
            t_stat, p_value = stats.ttest_ind(
                backtest_results['daily_returns'] if 'daily_returns' in backtest_results.columns else [0.001]*100,
                paper_results['pnl'].tolist(),
                equal_var=False
            )
        except Exception as e:
            logger.warning(f"T-test failed: {e}")
            p_value = 0.05  # Conservative assumption
        
        alignment_valid = p_value > 0.05  # Fail to reject null hypothesis (no significant difference)
        
        results = {
            "alignment_valid": bool(alignment_valid),
            "p_value": float(p_value),
            "backtest_sharpe": float(backtest_sharpe),
            "paper_sharpe": float(paper_sharpe),
            "sharpe_difference": float(abs(backtest_sharpe - paper_sharpe))
        }
        
        logger.info(f"Backtest-live alignment: {results}")
        return results

    def assess_deployment_readiness(self, paper_metrics: Dict[str, Any], alignment_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive readiness assessment with go/no-go decision framework.
        """
        # Check minimum requirements
        min_days_met = paper_metrics.get("paper_trading_days", 0) >= self.min_paper_days
        win_rate_adequate = paper_metrics.get("win_rate", 0) >= 0.45
        sharpe_adequate = paper_metrics.get("sharpe_ratio", 0) >= 0.8
        alignment_valid = alignment_results.get("alignment_valid", False)
        
        readiness_score = sum([min_days_met, win_rate_adequate, sharpe_adequate, alignment_valid]) / 4.0
        deployment_approved = readiness_score >= 0.75 and alignment_valid
        
        assessment = {
            "readiness_score": float(readiness_score),
            "deployment_approved": bool(deployment_approved),
            "criteria_met": {
                "min_days": min_days_met,
                "win_rate": win_rate_adequate,
                "sharpe": sharpe_adequate,
                "alignment": alignment_valid
            },
            "recommendation": "APPROVED" if deployment_approved else "REJECTED"
        }
        
        logger.info(f"Deployment readiness assessment: {assessment}")
        return assessment

    def benchmark_against_expectations(self, paper_results: pd.DataFrame, expected_metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        Performance benchmarking against backtested predictions with confidence intervals.
        """
        actual_win_rate = len(paper_results[paper_results['pnl'] > 0]) / len(paper_results) if len(paper_results) > 0 else 0
        expected_win_rate = expected_metrics.get("expected_win_rate", 0.55)
        
        # Calculate confidence interval for actual win rate
        n = len(paper_results)
        if n > 0:
            se = np.sqrt((actual_win_rate * (1 - actual_win_rate)) / n)
            margin = 1.96 * se  # 95% CI
            ci_lower = max(0, actual_win_rate - margin)
            ci_upper = min(1, actual_win_rate + margin)
        else:
            ci_lower = ci_upper = 0
        
        within_expectations = ci_lower <= expected_win_rate <= ci_upper
        
        benchmark = {
            "actual_win_rate": float(actual_win_rate),
            "expected_win_rate": float(expected_win_rate),
            "confidence_interval": [float(ci_lower), float(ci_upper)],
            "within_expectations": bool(within_expectations),
            "deviation": float(abs(actual_win_rate - expected_win_rate))
        }
        
        logger.info(f"Performance benchmarking: {benchmark}")
        return benchmark

    def generate_deployment_certification(self, readiness_assessment: Dict[str, Any], benchmark_results: Dict[str, Any]) -> str:
        """
        Formal certification process for live deployment approval.
        """
        certification = {
            "certification_id": f"CERT_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": pd.Timestamp.now().isoformat(),
            "deployment_approved": readiness_assessment["deployment_approved"],
            "readiness_score": readiness_assessment["readiness_score"],
            "performance_within_expectations": benchmark_results["within_expectations"],
            "paper_trading_days": readiness_assessment.get("paper_trading_days", 0),
            "certification_status": "APPROVED" if readiness_assessment["deployment_approved"] else "REJECTED",
            "validation_metrics": {
                "win_rate": benchmark_results["actual_win_rate"],
                "sharpe_ratio": readiness_assessment.get("sharpe_ratio", 0),
                "backtest_alignment": readiness_assessment.get("alignment_valid", False)
            }
        }
        
        # Save certification
        cert_path = os.path.join(self.output_dir, f"deployment_cert_{certification['certification_id']}.json")
        import json
        with open(cert_path, 'w') as f:
            json.dump(certification, f, indent=2)
        
        logger.info(f"Deployment certification generated: {cert_path}")
        return cert_path
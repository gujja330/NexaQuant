import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any
from great_expectations.dataset import PandasDataset
from great_expectations.core import ExpectationSuite
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QualityGuardian:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Great Expectations-powered data validation with SPC for drift detection and auto-repair.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./data_engine/validated/"
        os.makedirs(self.output_dir, exist_ok=True)
        self.control_limit_sigma = self.config.get("data_quality", {}).get("control_limit_sigma", 3)
        self.repair_strategy = self.config.get("data_quality", {}).get("repair_strategy", "quarantine")

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def create_expectation_suite(self) -> ExpectationSuite:
        """Create comprehensive data quality expectations."""
        ge_df = PandasDataset()
        
        # Core expectations
        ge_df.expect_column_values_to_not_be_null("close")
        ge_df.expect_column_values_to_not_be_null("open")
        ge_df.expect_column_values_to_not_be_null("high")
        ge_df.expect_column_values_to_not_be_null("low")
        ge_df.expect_column_values_to_not_be_null("tick_volume")
        
        # Value range expectations
        ge_df.expect_column_values_to_be_between("close", 0, 1e8)
        ge_df.expect_column_values_to_be_between("open", 0, 1e8)
        ge_df.expect_column_values_to_be_between("high", 0, 1e8)
        ge_df.expect_column_values_to_be_between("low", 0, 1e8)
        ge_df.expect_column_values_to_be_between("tick_volume", 0, 1e9)
        
        # Temporal expectations
        ge_df.expect_column_values_to_be_unique("time")
        ge_df.expect_table_row_count_to_be_between(100, 1000000)
        
        return ge_df.get_expectation_suite()

    def validate_data_quality(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Validate data quality using Great Expectations."""
        if df.empty:
            return {"is_valid": False, "issues": ["Empty dataframe"], "repair_action": "quarantine"}
        
        # Convert to Great Expectations dataset
        ge_df = PandasDataset(df)
        suite = self.create_expectation_suite()
        validation_result = ge_df.validate(expectation_suite=suite)
        
        is_valid = validation_result.success
        issues = []
        
        for result in validation_result.results:
            if not result.success:
                issues.append(f"{result.expectation_config.expectation_type}: {result.result}")
        
        repair_action = "accept" if is_valid else self.repair_strategy
        
        logger.info(f"Quality validation for {symbol}: {'PASS' if is_valid else 'FAIL'}")
        return {
            "is_valid": is_valid,
            "issues": issues,
            "repair_action": repair_action,
            "validation_result": validation_result
        }

    def apply_statistical_process_control(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Apply SPC for drift detection using control charts."""
        if df.empty or len(df) < 20:
            return {"in_control": True, "drift_detected": False, "metrics": {}}
        
        # Calculate control limits for key metrics
        metrics = {}
        drift_detected = False
        
        for col in ['close', 'tick_volume']:
            if col in df.columns:
                data = df[col].dropna()
                if len(data) < 10:
                    continue
                
                mean = data.mean()
                std = data.std()
                ucl = mean + self.control_limit_sigma * std
                lcl = mean - self.control_limit_sigma * std
                
                # Check last 5 points for out-of-control signals
                recent_points = data.tail(5)
                out_of_control = (recent_points > ucl) | (recent_points < lcl)
                
                if out_of_control.any():
                    drift_detected = True
                
                metrics[col] = {
                    "mean": float(mean),
                    "std": float(std),
                    "ucl": float(ucl),
                    "lcl": float(lcl),
                    "out_of_control_points": int(out_of_control.sum())
                }
        
        logger.info(f"SPC for {symbol}: {'Drift detected' if drift_detected else 'In control'}")
        return {
            "in_control": not drift_detected,
            "drift_detected": drift_detected,
            "metrics": metrics
        }

    def auto_repair_data(self, df: pd.DataFrame, repair_action: str) -> pd.DataFrame:
        """Auto-repair or quarantine bad data based on configuration."""
        if repair_action == "quarantine":
            # In production, would move to quarantine directory
            logger.warning("Data quarantined due to quality issues")
            return pd.DataFrame()  # Return empty to indicate quarantine
        
        elif repair_action == "repair":
            # Apply basic repairs
            df = df.copy()
            
            # Fix negative prices
            for col in ['close', 'open', 'high', 'low']:
                if col in df.columns:
                    df[col] = df[col].clip(lower=0.0001)
            
            # Fix negative volume
            if 'tick_volume' in df.columns:
                df['tick_volume'] = df['tick_volume'].clip(lower=0)
            
            # Handle duplicates
            if 'time' in df.index.name or 'time' in df.columns:
                df = df[~df.index.duplicated(keep='first')]
            
            logger.info("Applied automatic data repairs")
            return df
        
        else:  # accept
            return df

    def validate_and_repair(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Main method to validate and repair data."""
        # Quality validation
        quality_result = self.validate_data_quality(df, symbol)
        
        # SPC validation
        spc_result = self.apply_statistical_process_control(df, symbol)
        
        # Determine final action
        if not quality_result["is_valid"] or spc_result["drift_detected"]:
            repaired_df = self.auto_repair_data(df, quality_result["repair_action"])
        else:
            repaired_df = df
        
        # Save validated data
        if not repaired_df.empty:
            output_path = os.path.join(self.output_dir, f"{symbol}_validated.parquet")
            repaired_df.to_parquet(output_path)
            logger.info(f"Saved validated data to {output_path}")
        
        return repaired_df
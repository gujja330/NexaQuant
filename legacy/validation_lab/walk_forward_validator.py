# validation_lab/walk_forward_validator.py
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List
from datetime import datetime, timedelta
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WalkForwardValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_config = config.get("validation", {})
        self.embargo_days = self.validation_config.get("embargo_days", 30)
        self.train_days = self.validation_config.get("walk_forward_train_days", 30)
        self.test_days = self.validation_config.get("walk_forward_test_days", 15)
        os.makedirs("validation_lab/results", exist_ok=True)

    def _empty_report(self) -> Dict[str, Any]:
        return {
            "total_folds": 0,
            "mean_test_sharpe": 0.0,
            "std_test_sharpe": 0.0,
            "mean_test_win_rate": 0.0,
            "std_test_win_rate": 0.0,
            "folds": [],
            "validation_timestamp": datetime.now().isoformat()
        }


    def create_temporal_splits(self, df: pd.DataFrame) -> List[Dict[str, pd.DataFrame]]:
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, unit='s')
        df = df.sort_index()
        
        if len(df) < 100:
            return []

        start = df.index[0]
        end = df.index[-1]
        
        train_days = self.validation_config.get("walk_forward_train_days", 90)
        test_days = self.validation_config.get("walk_forward_test_days", 30)
        embargo_days = self.validation_config.get("embargo_days", 7)
        
        min_required = train_days + embargo_days + test_days
        if (end - start).days < min_required:
            return []

        splits = []
        current = start
        while True:
            train_end = current + pd.Timedelta(days=train_days)
            embargo_start = train_end + pd.Timedelta(days=embargo_days)
            test_end = embargo_start + pd.Timedelta(days=test_days)
            if test_end > end:
                break

            train_df = df[(df.index >= current) & (df.index < train_end)]
            test_df = df[(df.index >= embargo_start) & (df.index < test_end)]
            
            # ✅ CRITICAL FIX: Require 30+ VALID bars (after indicator warm-up)
            if len(test_df) >= 30:
                splits.append({
                    "train": train_df,
                    "test": test_df,
                    "train_period": (current, train_end),
                    "test_period": (embargo_start, test_end)
                })
                current = test_end
            else:
                break
                
        return splits

    def execute_walk_forward_analysis(self, df_with_features: pd.DataFrame, symbol: str, timeframe: str = "H1") -> Dict[str, Any]:
        try:
            if not isinstance(df_with_features.index, pd.DatetimeIndex):
                df_with_features = df_with_features.copy()
                df_with_features.index = pd.to_datetime(df_with_features.index, unit='s')

            splits = self.create_temporal_splits(df_with_features)
            if not splits:
                logger.warning(f"No valid splits for {symbol} {timeframe}")
                return self._empty_report()

            from validation_lab.regime_aware_tester import RegimeAwareTester
            tester = RegimeAwareTester(self.config)

            results = []
            for i, split in enumerate(splits):
                test_df = split["test"].copy()
                if test_df.empty or len(test_df) < 10:
                    continue

                test_results = tester.execute_full_backtest_on_features(test_df, symbol, timeframe)
                results.append({
                    "fold": i + 1,
                    "train_period": [split["train_period"][0].isoformat(), split["train_period"][1].isoformat()],
                    "test_period": [split["test_period"][0].isoformat(), split["test_period"][1].isoformat()],
                    "test_metrics": {
                        "sharpe": test_results.get("sharpe_ratio", 0.0),
                        "win_rate": test_results.get("win_rate", 0.0),
                        "total_trades": test_results.get("total_trades", 0)
                    }
                })

            if not results:
                return self._empty_report()

            sharpe_values = [r["test_metrics"]["sharpe"] for r in results]
            win_rates = [r["test_metrics"]["win_rate"] for r in results]

            report = {
                "total_folds": len(results),
                "mean_test_sharpe": float(np.mean(sharpe_values)) if sharpe_values else 0.0,
                "std_test_sharpe": float(np.std(sharpe_values)) if len(sharpe_values) > 1 else 0.0,
                "mean_test_win_rate": float(np.mean(win_rates)) if win_rates else 0.0,
                "std_test_win_rate": float(np.std(win_rates)) if len(win_rates) > 1 else 0.0,
                "folds": results,
                "validation_timestamp": datetime.now().isoformat()
            }

            result_path = os.path.join(
                "validation_lab", 
                "results", 
                f"walk_forward_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(result_path, "w") as f:
                json.dump(report, f, indent=2)
            logger.info(f"Walk-forward validation completed. Results saved to: {result_path}")
            return report

        except Exception as e:
            logger.error(f"Walk-forward analysis failed for {symbol} {timeframe}: {e}", exc_info=True)
            return self._empty_report()
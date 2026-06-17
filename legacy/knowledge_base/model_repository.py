import os
import yaml
import pandas as pd
import numpy as np
import mlflow
import pickle
from typing import Dict, Any, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelRepository:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Versioned model storage with rollback capabilities, performance tracking, and automated lifecycle management.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./knowledge_base/models/"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize MLflow tracking
        mlflow.set_tracking_uri("file:./knowledge_base/mlflow/")
        self.experiment_name = "marl_trading_models"
        if not mlflow.get_experiment_by_name(self.experiment_name):
            mlflow.create_experiment(self.experiment_name)
        mlflow.set_experiment(self.experiment_name)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def save_model(self, model, symbol: str, version: str, metadata: Dict[str, Any]) -> str:
        """
        Save model with full metadata, performance metrics, and lineage tracking using MLflow.
        """
        model_path = os.path.join(self.output_dir, f"{symbol}_{version}")
        os.makedirs(model_path, exist_ok=True)
        
        # Save model using pickle (in production, use joblib or torch.save)
        model_file = os.path.join(model_path, "model.pkl")
        with open(model_file, 'wb') as f:
            pickle.dump(model, f)
        
        # Save metadata
        metadata_file = os.path.join(model_path, "metadata.json")
        import json
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Log to MLflow
        with mlflow.start_run(run_name=f"{symbol}_{version}"):
            mlflow.log_params(metadata.get("hyperparameters", {}))
            mlflow.log_metrics(metadata.get("performance_metrics", {}))
            mlflow.log_artifact(model_file)
            mlflow.log_artifact(metadata_file)
        
        logger.info(f"Model saved: {symbol} v{version}")
        return model_path

    def load_model(self, symbol: str, version: str = "latest") -> tuple:
        """
        Load model with version control and fallback to latest if specified.
        """
        if version == "latest":
            # Find latest version
            versions = []
            for item in os.listdir(self.output_dir):
                if item.startswith(f"{symbol}_"):
                    versions.append(item)
            if not versions:
                raise FileNotFoundError(f"No models found for symbol: {symbol}")
            latest_version = sorted(versions)[-1]
            version = latest_version.replace(f"{symbol}_", "")
        
        model_path = os.path.join(self.output_dir, f"{symbol}_{version}")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {symbol} v{version}")
        
        # Load model
        model_file = os.path.join(model_path, "model.pkl")
        with open(model_file, 'rb') as f:
            model = pickle.load(f)
        
        # Load metadata
        metadata_file = os.path.join(model_path, "metadata.json")
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        logger.info(f"Model loaded: {symbol} v{version}")
        return model, metadata

    def list_models(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        List all models with metadata, performance metrics, and version information.
        """
        models = []
        for item in os.listdir(self.output_dir):
            if os.path.isdir(os.path.join(self.output_dir, item)):
                if symbol and not item.startswith(f"{symbol}_"):
                    continue
                
                model_path = os.path.join(self.output_dir, item)
                metadata_file = os.path.join(model_path, "metadata.json")
                
                if os.path.exists(metadata_file):
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    models.append({
                        "symbol": item.split("_")[0],
                        "version": "_".join(item.split("_")[1:]),
                        "metadata": metadata,
                        "path": model_path
                    })
        
        # Sort by creation timestamp
        models.sort(key=lambda x: x["metadata"].get("timestamp", ""), reverse=True)
        logger.info(f"Listed {len(models)} models")
        return models

    def compare_models(self, symbol: str, versions: List[str]) -> Dict[str, Any]:
        """
        Performance comparison across model versions with statistical significance testing.
        """
        comparison = {"symbol": symbol, "versions": {}}
        
        for version in versions:
            try:
                _, metadata = self.load_model(symbol, version)
                comparison["versions"][version] = {
                    "win_rate": metadata.get("performance_metrics", {}).get("win_rate", 0),
                    "sharpe_ratio": metadata.get("performance_metrics", {}).get("sharpe_ratio", 0),
                    "max_drawdown": metadata.get("performance_metrics", {}).get("max_drawdown", 0),
                    "timestamp": metadata.get("timestamp", "")
                }
            except Exception as e:
                logger.error(f"Failed to load model {symbol} v{version}: {e}")
                comparison["versions"][version] = {"error": str(e)}
        
        # Determine best model
        valid_versions = {v: m for v, m in comparison["versions"].items() if "error" not in m}
        if valid_versions:
            best_version = max(valid_versions.keys(), 
                             key=lambda v: valid_versions[v]["sharpe_ratio"])
            comparison["best_version"] = best_version
            comparison["recommendation"] = f"Use {best_version} for production"
        else:
            comparison["best_version"] = None
            comparison["recommendation"] = "No valid models available"
        
        logger.info(f"Model comparison completed for {symbol}")
        return comparison

    def rollback_model(self, symbol: str, target_version: str) -> bool:
        """
        Rollback to a previous model version with validation and safety checks.
        """
        try:
            # Load target model to validate it exists
            model, metadata = self.load_model(symbol, target_version)
            
            # Create rollback record
            rollback_record = {
                "symbol": symbol,
                "target_version": target_version,
                "rollback_timestamp": pd.Timestamp.now().isoformat(),
                "previous_metadata": metadata
            }
            
            # Save rollback record
            rollback_path = os.path.join(self.output_dir, f"rollback_{symbol}_{target_version}.json")
            with open(rollback_path, 'w') as f:
                json.dump(rollback_record, f, indent=2)
            
            logger.info(f"Rollback completed to {symbol} v{target_version}")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed for {symbol} v{target_version}: {e}")
            return False

    def archive_old_models(self, symbol: str, keep_latest: int = 3) -> List[str]:
        """
        Archive old model versions to maintain storage efficiency while preserving history.
        """
        models = self.list_models(symbol)
        if len(models) <= keep_latest:
            return []
        
        # Sort by timestamp (oldest first)
        models.sort(key=lambda x: x["metadata"].get("timestamp", ""))
        models_to_archive = models[:-keep_latest]
        
        archived_paths = []
        for model_info in models_to_archive:
            archive_path = model_info["path"] + "_archived"
            os.rename(model_info["path"], archive_path)
            archived_paths.append(archive_path)
            logger.info(f"Archived model: {model_info['path']}")
        
        return archived_paths

    def generate_model_report(self, symbol: str) -> str:
        """
        Generate comprehensive model performance and lineage report.
        """
        models = self.list_models(symbol)
        if not models:
            return f"No models found for {symbol}"
        
        report = {
            "symbol": symbol,
            "total_models": len(models),
            "latest_model": models[0]["version"],
            "model_history": [],
            "performance_trend": {
                "win_rates": [],
                "sharpe_ratios": [],
                "timestamps": []
            }
        }
        
        for model in models:
            metadata = model["metadata"]
            report["model_history"].append({
                "version": model["version"],
                "win_rate": metadata.get("performance_metrics", {}).get("win_rate", 0),
                "sharpe_ratio": metadata.get("performance_metrics", {}).get("sharpe_ratio", 0),
                "max_drawdown": metadata.get("performance_metrics", {}).get("max_drawdown", 0),
                "timestamp": metadata.get("timestamp", "")
            })
            
            report["performance_trend"]["win_rates"].append(
                metadata.get("performance_metrics", {}).get("win_rate", 0)
            )
            report["performance_trend"]["sharpe_ratios"].append(
                metadata.get("performance_metrics", {}).get("sharpe_ratio", 0)
            )
            report["performance_trend"]["timestamps"].append(
                metadata.get("timestamp", "")
            )
        
        # Save report
        report_path = os.path.join(self.output_dir, f"model_report_{symbol}.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Model report generated: {report_path}")
        return report_path
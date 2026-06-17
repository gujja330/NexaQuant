import os
import yaml
import pandas as pd
import json
from datetime import datetime
from typing import Dict, Any, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataLineageTracker:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        """
        Full data provenance tracking from source to agent decision with audit trail.
        All parameters dynamically loaded from config with zero symbol hardcoding.
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.symbols = self.config["system"]["symbols"]
        self.output_dir = "./data_engine/lineage/"
        os.makedirs(self.output_dir, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Dynamically load configuration from YAML."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def create_lineage_record(self, 
                            source: str, 
                            symbol: str, 
                            operation: str, 
                            input_files: List[str], 
                            output_files: List[str],
                            metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a comprehensive lineage record for data provenance."""
        record = {
            "lineage_id": f"{symbol}_{operation}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "symbol": symbol,
            "operation": operation,
            "input_files": input_files,
            "output_files": output_files,
            "metadata": metadata or {},
            "config_hash": self._hash_config(),
            "version": self.config.get("system", {}).get("version", "1.0")
        }
        return record

    def _hash_config(self) -> str:
        """Create a hash of the current configuration for reproducibility."""
        import hashlib
        config_str = json.dumps(self.config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:16]

    def track_data_flow(self, symbol: str, stage: str, inputs: List[str], outputs: List[str]) -> str:
        """Track data flow through the pipeline with comprehensive metadata."""
        metadata = {
            "stage": stage,
            "symbols": [symbol],
            "timeframes": self.config["system"]["timeframes"],
            "processing_date": datetime.now().isoformat(),
            "user": os.getenv("USER", "system")
        }
        
        # Determine source based on stage
        if stage == "collection":
            source = "MT5_API"
        elif stage == "synthetic":
            source = "Synthetic_Generator"
        elif stage == "feature_engineering":
            source = "Feature_Forge"
        elif stage == "agent_decision":
            source = "Multi_Agent_Brain"
        else:
            source = "Unknown"
        
        record = self.create_lineage_record(source, symbol, stage, inputs, outputs, metadata)
        
        # Save lineage record
        record_path = os.path.join(self.output_dir, f"{record['lineage_id']}.json")
        with open(record_path, 'w') as f:
            json.dump(record, f, indent=2)
        
        logger.info(f"Tracked data lineage: {record['lineage_id']}")
        return record_path

    def generate_audit_trail(self, symbol: str) -> List[Dict[str, Any]]:
        """Generate comprehensive audit trail for regulatory compliance."""
        audit_trail = []
        lineage_files = [f for f in os.listdir(self.output_dir) if f.startswith(symbol) and f.endswith('.json')]
        
        for file in sorted(lineage_files):
            file_path = os.path.join(self.output_dir, file)
            with open(file_path, 'r') as f:
                record = json.load(f)
                audit_trail.append(record)
        
        # Sort by timestamp
        audit_trail.sort(key=lambda x: x['timestamp'])
        logger.info(f"Generated audit trail with {len(audit_trail)} records for {symbol}")
        return audit_trail

    def validate_lineage_integrity(self, symbol: str) -> bool:
        """Validate lineage integrity by checking for gaps in the data flow."""
        audit_trail = self.generate_audit_trail(symbol)
        if len(audit_trail) == 0:
            logger.warning(f"No lineage records found for {symbol}")
            return False
        
        expected_stages = ["collection", "feature_engineering", "agent_decision"]
        actual_stages = [record["operation"] for record in audit_trail]
        
        missing_stages = set(expected_stages) - set(actual_stages)
        if missing_stages:
            logger.warning(f"Missing stages in lineage for {symbol}: {missing_stages}")
            return False
        
        logger.info(f"Lineage integrity validated for {symbol}")
        return True

    def export_compliance_report(self, symbol: str) -> str:
        """Export compliance report for regulatory requirements."""
        audit_trail = self.generate_audit_trail(symbol)
        compliance_report = {
            "report_id": f"compliance_{symbol}_{datetime.now().strftime('%Y%m%d')}",
            "symbol": symbol,
            "generation_date": datetime.now().isoformat(),
            "total_records": len(audit_trail),
            "data_sources": list(set(record["source"] for record in audit_trail)),
            "processing_stages": list(set(record["operation"] for record in audit_trail)),
            "compliance_status": "COMPLIANT" if self.validate_lineage_integrity(symbol) else "NON_COMPLIANT",
            "audit_trail": audit_trail
        }
        
        report_path = os.path.join(self.output_dir, f"compliance_report_{symbol}.json")
        with open(report_path, 'w') as f:
            json.dump(compliance_report, f, indent=2)
        
        logger.info(f"Exported compliance report to {report_path}")
        return report_path
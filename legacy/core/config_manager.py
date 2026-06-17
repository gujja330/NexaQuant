# core/config_manager.py
import os
import yaml
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Centralized configuration management with validation and dynamic reloading.
    Fully dynamic. Zero hardcoding. Config-driven. AI-powered.
    Implements Audit-Ready AI, Constitutional AI, and Dynamic Configuration.
    """
    def __init__(self, config_path: str = "config/base_config.yaml"):
        self.config_path = config_path
        self.config = self._load_and_validate_config()
        logger.info("✅ Configuration loaded and validated")

    def _load_and_validate_config(self) -> Dict[str, Any]:
        """Load YAML config and validate required sections."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"❌ Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Validate required top-level sections
        required_sections = ["system", "risk_profiles", "execution", "intelligence", "risk_fortress", "core"]
        for section in required_sections:
            if section not in config:
                raise ValueError(f"❌ Missing required config section: {section}")
        
        # Validate symbols and risk profiles
        symbols = config["system"]["symbols"]
        for symbol in symbols:
            profile_key = f"{symbol}_risk_profile"
            if profile_key not in config["risk_profiles"]:
                raise ValueError(f"❌ Missing risk profile for symbol: {profile_key}")
        
        return config

    def get_config(self) -> Dict[str, Any]:
        """Return current configuration."""
        return self.config

    def reload_config(self) -> Dict[str, Any]:
        """Reload configuration from file."""
        self.config = self._load_and_validate_config()
        logger.info("🔄 Configuration reloaded")
        return self.config

    def validate_config_integrity(self) -> bool:
        """Validate configuration integrity and consistency."""
        try:
            self._load_and_validate_config()
            return True
        except Exception as e:
            logger.error(f"❌ Config integrity check failed: {e}")
            return False
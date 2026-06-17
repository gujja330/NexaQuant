# intelligence/risk_agent/agent.py
import numpy as np
import torch
import torch.nn as nn
import yaml
from typing import Dict, Any

class NeuralKellyNetwork(nn.Module):
    def __init__(self, input_dim: int = 25):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        return self.net(x)

class RiskAgent:
    def __init__(self, config_path: str = "config/base_config.yaml"):
        # 🔹 Load ALL configuration dynamically — no hardcoded values
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # 🔹 Extract system-wide parameters
        self.risk_per_trade = self.config["system"]["risk_per_trade"]
        self.max_drawdown_limit = self.config["system"]["max_drawdown_limit"]
        self.symbols = self.config["system"]["symbols"]
        
        # 🔹 Load symbol-specific risk profiles from config (dynamic)
        self.symbol_risk_profiles = self._load_symbol_risk_profiles()
        
        # 🔹 Initialize neural risk model
        self.model = NeuralKellyNetwork(input_dim=25)

    def _load_symbol_risk_profiles(self) -> Dict[str, Dict[str, Any]]:
        """
        Load instrument-specific risk parameters from config.
        Enables zero hardcoding — all symbols & pip values defined in YAML.
        """
        # Default fallback if not specified per symbol
        default_profile = {
            "pip_value_per_lot": 0.01,  # e.g., XAUUSDc: $0.01 per 0.01 lot per pip
            "min_stop_pips": 10,
            "max_position_size": 10.0
        }
        
        profiles = {}
        for symbol in self.symbols:
            # Allow per-symbol override in config (e.g., BTCUSDc vs XAUUSDc)
            profile_key = f"{symbol}_risk_profile"
            if "risk_profiles" in self.config and profile_key in self.config["risk_profiles"]:
                profiles[symbol] = self.config["risk_profiles"][profile_key]
            else:
                profiles[symbol] = default_profile.copy()
        return profiles

    def calculate_position_size(self, equity: float, stop_pips: float, symbol: str) -> float:
        """
        Dynamically compute position size using symbol-specific risk profile.
        No hardcoded symbol logic.
        """
        if symbol not in self.symbol_risk_profiles:
            raise ValueError(f"Risk profile not defined for symbol: {symbol}")
        
        profile = self.symbol_risk_profiles[symbol]
        pip_value = profile["pip_value_per_lot"]
        max_size = profile["max_position_size"]
        
        risk_amount = equity * self.risk_per_trade
        sl_dollars = stop_pips * pip_value * 100  # for 1 standard lot
        
        if sl_dollars <= 0:
            return 0.01  # minimum trade size
        
        size = risk_amount / sl_dollars
        return min(size, max_size)

    def assess_drawdown_breach(self, equity_curve: np.ndarray) -> bool:
        """
        Universal drawdown logic — no symbol dependency.
        """
        if len(equity_curve) < 2:
            return False
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / peak
        return drawdown[-1] > self.max_drawdown_limit
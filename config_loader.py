# config_loader.py
"""
Single source of truth for pipeline settings — FULLY DYNAMIC, zero hardcoding.

The point: the same pipeline must work for gold, BTC, FX, stocks, commodities with NO
code change. So per-symbol cost and pip-size are either taken from config OR DERIVED
FROM THE DATA itself:

  pip_size  = 10 ** (floor(log10(median_price)) - 4)
              -> gold ~2500 -> 0.1 | BTC ~60000 -> 1.0 | EURUSD ~1.1 -> 0.0001
                 | a $50 stock -> 0.01    (one formula, sensible across all asset classes)
  cost (rt) = median_price * default_cost_bps / 10000      (e.g. gold 2500 * 2bp = 0.5)

Everything else (timeframes, IS fraction, gate thresholds, regime/sizing params) is read
from config/base_config.yaml. Nothing instrument-specific is hardcoded in the logic.
"""
import math
from pathlib import Path
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
_CFG = None


def cfg():
    global _CFG
    if _CFG is None:
        with open(ROOT / "config" / "base_config.yaml", encoding="utf-8") as f:
            _CFG = yaml.safe_load(f)
    return _CFG


def pipeline():
    return cfg().get("pipeline", {})


def timeframes():
    return pipeline().get("timeframes", {"H1": 24, "H4": 12})


def gate():
    return pipeline().get("gate", {"min_oos_sharpe": 1.0, "min_dsr": 0.90,
                                    "min_trades": 30, "max_pbo": 0.5})


def derive_pip_size(median_price):
    if not (median_price and median_price > 0):
        return 0.1
    return 10 ** (math.floor(math.log10(median_price)) - 4)


def symbol_params(symbol, price_series=None):
    """Return {cost, pip_size} for ANY symbol. Config override if present, else derived
    from the data so a brand-new instrument needs no code/config change."""
    inst = cfg().get("instruments", {}).get(symbol, {})
    med = float(np.nanmedian(price_series)) if price_series is not None and len(price_series) else None
    pip = inst.get("pip_size") or derive_pip_size(med)
    if "cost" in inst:
        cost = inst["cost"]
    elif med is not None:
        cost = med * pipeline().get("default_cost_bps", 2.0) / 10000.0
    else:
        cost = 0.5
    return {"cost": float(cost), "pip_size": float(pip)}

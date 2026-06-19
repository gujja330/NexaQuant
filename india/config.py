# india/config.py
"""
Central ARJUNA v2 configuration — the ONE place to change strategy behavior (dynamic format).
Every core module + the runner reads from CONFIG, so tuning the system never means editing logic.
"""
from dataclasses import dataclass


@dataclass
class ArjunaConfig:
    # --- universe ---
    universe: str = "nifty200"        # "nifty100" | "nifty200"
    # --- rebalance / risk windows ---
    rebal_days: int = 21              # 21 = monthly, 63 = quarterly
    lookback: int = 120               # trading days for volatility / covariance
    # --- portfolio construction (Layer 4) ---
    method: str = "hrp"               # "ew" | "inv_vol" | "min_var" | "hrp" (validated champion)
    name_cap: float = 0.05            # max weight per stock (diversification)
    # --- regime / exposure (Layer 1) ---
    regime: str = "global"            # "none" | "simple" | "global" (simple+Global Risk) | "hmm"
    # --- execution (Layer 4) ---
    news_filter: bool = True          # drop strongly-negative-news names (blow-up filter)
    news_thresh: float = -0.4
    cost_bps: float = 21.0            # round-trip cost
    capital: float = 100000.0


CONFIG = ArjunaConfig()


def universe_list():
    from india.data_nse import NIFTY100, NIFTY200
    return NIFTY100 if CONFIG.universe == "nifty100" else NIFTY200

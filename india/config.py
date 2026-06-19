# india/config.py
"""
Central ARJUNA v2 configuration — the ONE place to change strategy behavior (dynamic format).
Every core module + the runner reads from CONFIG, so tuning the system never means editing logic.

>>> ARJUNA CORE v2.1 — FROZEN 2026-06-19 <<<
Champion: HRP + continuous regime + Global Risk, QUARTERLY rebalance, 15 stocks, sector<=3.
Validated: Sharpe 2.00 · maxDD 10.6% · turnover 3.3/yr · Deflated Sharpe 0.996 · PBO 0.00.
Stress (real corrections): positive in 3/4, drawdown 2-3x smaller than Nifty. Monte-Carlo (35%
haircut): median ~9-10%/yr, P(+ve 1yr)=87%/3yr=98%, typical maxDD 6-8%, P(DD>20%)~0%.
Locked for 12-month forward paper. DO NOT tune Core — experiments live in india/research/ (Lab).
"""
from dataclasses import dataclass

VERSION = "ARJUNA Core v2.1 (frozen 2026-06-19)"


@dataclass
class ArjunaConfig:
    # --- universe ---
    universe: str = "nifty200"        # "nifty100" | "nifty200"
    # --- investor inputs (master-prompt spec) ---
    risk_appetite: str = "medium"     # "low" | "medium" | "high"  -> sets method/cap/regime
    max_drawdown: float = 0.10        # tolerance (informational + tightens de-risk when low)
    sector_cap: float = 0.20          # max weight per sector
    position_cap: float = 0.25        # hard ceiling per stock
    # --- rebalance / risk windows ---
    rebal_days: int = 63              # QUARTERLY (promoted: Sharpe 1.86 vs monthly 1.70, less churn)
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

# risk_appetite -> (method, name_cap, regime). Low = diversified+defensive, High = concentrated.
RISK_PROFILE = {"low": ("hrp", 0.04, "global"),
                "medium": ("hrp", 0.05, "global"),
                "high": ("inv_vol", 0.08, "simple")}


def apply_risk_appetite():
    m, cap, reg = RISK_PROFILE.get(CONFIG.risk_appetite, RISK_PROFILE["medium"])
    CONFIG.method, CONFIG.name_cap, CONFIG.regime = m, cap, reg


def universe_list():
    from india.data_nse import NIFTY100, NIFTY200
    return NIFTY100 if CONFIG.universe == "nifty100" else NIFTY200

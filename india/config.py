# india/config.py
"""
Central ARJUNA v2 configuration — the ONE place to change strategy behavior (dynamic format).
Every core module + the runner reads from CONFIG, so tuning the system never means editing logic.

>>> ARJUNA CORE v2.2 — 2026-06-22 <<<
DECOMPOSITION FINDING (see docs/ARJUNA_STRATEGY_DECISION.md): stock SELECTION and HRP WEIGHTING
add ~no value over equal-weight (HRP-15 Sharpe 1.28 ~ EW-15 1.30, regime OFF). The ENTIRE
Sharpe-2.0 edge is the REGIME overlay (defensive exposure timing). So v2.2 offers two validated
styles built on that one real edge:

  BROAD  (higher return, index-fund route): equal-weight the whole basket + regime.
         CAGR 20.6% · Sharpe 1.98 · DD 12.8% · DSR 0.992 · robust cross-period & on Nifty-100 (19.3%).
         Implement as an equal-weight / broad index fund + the regime cash rule. Best POTENTIAL.
  CONCENTRATED (individual-stock route): 15 names + regime (the v2.1 champion).
         CAGR 16.4% · Sharpe 2.02 · DD 11.2% · DSR 0.995. For holding specific shares / small capital;
         costs ~4pp CAGR vs BROAD — the price of holding 15 names instead of the whole basket.

CAVEAT: all CAGR is survivorship-inflated; BROAD is the MOST flattered (holds every survivor), so the
forward return gap over CONCENTRATED is likely smaller than +4pp. Sharpe parity is the honest read.
DO NOT re-defend HRP/selection as alpha — tested, dead. The edge to protect is the regime overlay.
Concluded experiments are archived in india/evidence/ (the evidence trail); reopened ML work (only
when a data trigger fires) starts fresh in india/lab/. See docs/ARJUNA_V4_ROADMAP.md.
"""
from dataclasses import dataclass

VERSION = "ARJUNA Core v2.2 (2026-06-22)"

# AI/ML re-experimentation policy (see docs/ARJUNA_V4_ROADMAP.md). We are NOT abandoning ML.
# It is a signboard, not a tombstone: TEMPORARILY CLOSED until better DATA arrives. Doctrine =
# Data -> Features -> Targets -> Validation -> Models (sophistication LAST). Run india/ai_reopen.py
# to see which data triggers are CLOSED vs ARMED.
MODELS_FROZEN_UNTIL_DATA_ARRIVES = True      # never *_FOREVER


@dataclass
class ArjunaConfig:
    # --- universe ---
    universe: str = "nifty200"        # "nifty100" | "nifty200"
    # --- STYLE: the v2.2 decision. "broad" = EW whole basket + regime (higher return, index-fund
    #     route). "concentrated" = 15 names + regime (individual-stock route, v2.1 champion). ---
    style: str = "concentrated"       # "broad" | "concentrated"
    topn: int = 15                    # names held in CONCENTRATED style (ignored when broad)
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


# style -> backtest kwargs. BROAD drops selection (topn=None) and uses equal-weight; the regime
# overlay (the one real edge) stays ON for both. See docs/ARJUNA_STRATEGY_DECISION.md.
def style_kwargs():
    if CONFIG.style == "broad":
        return dict(method="ew", regime=CONFIG.regime, topn=None, sector_cap=None,
                    rebal=CONFIG.rebal_days, cost_bps=CONFIG.cost_bps)
    return dict(method=CONFIG.method, regime=CONFIG.regime, topn=CONFIG.topn, sector_cap=2,
                rebal=CONFIG.rebal_days, cost_bps=CONFIG.cost_bps)


def universe_list():
    from india.data_nse import NIFTY100, NIFTY200
    return NIFTY100 if CONFIG.universe == "nifty100" else NIFTY200

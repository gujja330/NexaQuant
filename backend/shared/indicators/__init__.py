"""backend.shared.indicators — canonical single-implementation indicator library.

Constitution Article 30 · one canonical implementation per shared computation.
Any local reimplementation of a primitive here is a Constitutional violation.

Populated Wave Y · 2026-07-27.

Available primitives:
    rsi              rsi_series        (RSI-14 · simple + Wilder methods)
    atr_pct          atr_series        (true-range ATR from H/L/C)
    adx                                 (textbook Wilder ADX)
    macd                               (12/26/9 default · configurable)
    ema              ema_last          (EWM span variant)
    sma              sma_last          (rolling window)
    volatility_daily · volatility_annualized  (with TRADING_DAYS_YEAR=252)
    returns_pct      returns_series    (point-to-point + full series)
    max_drawdown_pct                    (rolling max drawdown)
"""
from __future__ import annotations

from backend.shared.indicators.rsi         import rsi, rsi_series  # noqa: F401
from backend.shared.indicators.atr         import atr_pct, atr_series  # noqa: F401
from backend.shared.indicators.adx         import adx  # noqa: F401
from backend.shared.indicators.macd        import macd  # noqa: F401
from backend.shared.indicators.ema         import ema, ema_last  # noqa: F401
from backend.shared.indicators.sma         import sma, sma_last  # noqa: F401
from backend.shared.indicators.volatility  import volatility_daily, volatility_annualized  # noqa: F401
from backend.shared.indicators.returns     import returns_pct, returns_series  # noqa: F401
from backend.shared.indicators.drawdown    import max_drawdown_pct  # noqa: F401

__version__ = "1.0.0"
__constitution__ = "Article 30"
__layer__ = "10_shared"
__populated_wave__ = "Y"

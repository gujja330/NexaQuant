"""Market Intelligence — market-level signals (not per-stock).

Reads only canonical data (via backend/canonical/adapters.py). Produces
a per-market snapshot: regime, breadth, volatility, liquidity, macro,
sector rotation, and a composite Market Health score.

Deterministic engine — no random state, no external API calls, no LLM.
For walk-forward replay: pass a cutoff date to `run()` and every input
is filtered on-or-before that date.
"""

from backend.market_intelligence.engine import MarketIntelligenceEngine   # noqa: F401

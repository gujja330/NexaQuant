# AEGIS core — market-agnostic layer. One engine, many markets via thin MarketAdapters.
# India = a non-invasive wrapper over the FROZEN india/ code; USA = a new adapter. Nothing here
# modifies India production.
from core.market_adapter import MarketAdapter, IndiaAdapter, USAAdapter, get_adapter  # noqa: F401

# india/ — PARALLEL module for Indian equities (NSE), kept separate from the gold/BTC system.
# Reuses the validated strategy logic (trend / breakout / regime) but has its own data,
# universe, validation, and (later) broker adapters (Angel One / Upstox). Nothing here
# imports into or changes the existing strategy/execution code.

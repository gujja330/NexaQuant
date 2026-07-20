"""Canonical Data Model (per architectural insertion approved 2026-07-20).

Normalizes market-specific quirks (currency, timezone, symbol format,
exchange codes, corporate action shape) into one internal schema so
downstream engines (market intelligence, investment intelligence,
fusion, comparison, portfolio) operate on the same primitives.

Sprint 1 scope: expose the CanonicalDatasetSpec + MarketProfile types
that datasets.yaml validates against. Adapter implementations (india
→ canonical, usa → canonical) land in later sprints.
"""
from .model import MarketProfile, CanonicalDatasetSpec, INDIA_PROFILE, USA_PROFILE   # noqa: F401

"""AEGIS Backend Data Foundation.

Sprint 1 · shared backend framework for BOTH India + USA. Provides:
- validation/  — freshness, schema, completeness, quality, confidence,
                  lineage validators + orchestrating pipeline
- canonical/   — cross-market canonical dataset spec (currency, tz,
                  symbol format normalizer)

Consumed by india/backend_validation/run.py and usa/backend_validation/run.py.
Both use the same shared framework — market-specific quirks live in each
market's datasets.yaml.
"""

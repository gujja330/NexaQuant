"""Winner Genome · per-candidate feature attribution.

Fields declared as per CEO 2026-09-03 master prompt. Each field is either:
  - AVAILABLE  (populated today)
  - ENRICHER   (waiting on a named enricher · noted with source)
  - NONE_YET   (no source in repo · would need a new detector)

The 'available' subset is what the Winner Genome extractor emits today.
The rest are documented so a future turn can expand coverage without
guessing at what the PDF actually asks for.
"""
from __future__ import annotations


WINNER_GENOME_FIELDS = {
    # Identity
    "position_or_candidate_id":       "AVAILABLE · Position ID (Registry) or synthetic candidate_id",
    "market":                         "AVAILABLE",
    "date":                           "AVAILABLE · decision date",
    "ticker":                         "AVAILABLE",
    "pit_universe_membership":        "AVAILABLE · PIT universe audit",

    # Selection
    "runner":                         "AVAILABLE",
    "rank":                           "AVAILABLE · from recommendations_v3.json rank",
    "rank_percentile":                "AVAILABLE · derived",
    "model_score":                    "AVAILABLE · ensemble_score",
    "confidence":                     "AVAILABLE · calibrated_confidence",

    # Context (partial · enrichers land more)
    "sector":                         "AVAILABLE · from Outcome Dataset",
    "industry":                       "AVAILABLE",
    "cap_bucket":                     "ENRICHER · B3 · yfinance-driven",
    "investability":                  "ENRICHER · B3 · parquet ADV",
    "market_regime":                  "ENRICHER · B1 · regime_at_entry",
    "sector_regime":                  "ENRICHER · B4 · sector_regime_score",
    "market_breadth":                 "NONE_YET · needs breadth calculator",
    "sector_breadth":                 "NONE_YET",
    "relative_sector_strength":       "ENRICHER · B4 output implicit",

    # News/macro/tech
    "news_sentiment":                 "ENRICHER · news adapter (USA Week-3 slot)",
    "news_severity":                  "NONE_YET",
    "macro_risk":                     "PARTIAL · macro_regime.json evidence blob",
    "technical_trend":                "PARTIAL · derivable from parquet",
    "momentum":                       "PARTIAL · short_term_momentum output",
    "rsi_14":                         "PARTIAL · short_term_momentum output",
    "ma20_50_200_distance":           "AVAILABLE · derivable from parquet",
    "volatility":                     "AVAILABLE · annualized_vol from momentum output",
    "liquidity":                      "AVAILABLE · ADV from B3",

    # Risk / portfolio
    "valuation":                      "ENRICHER · Fundamentals L2 (needs B6 batch)",
    "expected_alpha":                 "AVAILABLE · ensemble_score proxy",
    "risk_score":                     "PARTIAL · dynamic_risk_v2 output",
    "entry_zone_quality":             "AVAILABLE · momentum ledger entry_zone",
    "stop_distance":                  "AVAILABLE · from dynamic_risk_v2 stop",
    "target_distance":                "AVAILABLE · from ATR-fallback target",
    "portfolio_exposure":             "NONE_YET · needs portfolio state PIT",
    "correlation_exposure":           "NONE_YET",

    # Fundamentals L1 (Quality)
    "piotroski_f":                    "ENRICHER · B6 batch pending",
    "beneish_m":                      "ENRICHER · B6",
    "altman_z":                       "ENRICHER · B6",
    "sloan_accruals":                 "ENRICHER · B6",
    "interest_coverage":              "ENRICHER · B6",
    # Fundamentals L2 (Value)
    "fcf_yield":                      "ENRICHER · B6",
    "ev_ebitda":                      "ENRICHER · B6",
    "total_shareholder_yield":        "ENRICHER · B6",
    "sector_rel_value_rank":          "ENRICHER · B6",
    # Fundamentals L3 (Change · 5 · added 13F per CEO GAP 1)
    "analyst_rev_momentum":           "ENRICHER · B6",
    "guidance_rev":                   "ENRICHER · B6",
    "earnings_surprise":              "ENRICHER · B6",
    "insider_f4_signal":              "ENRICHER · B6",
    "inst_13f_change":                "ENRICHER · B6",
    # Fundamentals L4 (Flow)
    "fii_dii_net_flow_z":             "NONE_YET · NSE FII/DII API needed",
    "options_pcr":                    "NONE_YET",
    "short_interest_pct":             "ENRICHER · B6",
    # Fundamentals L5 (Event · India-only pledge)
    "earnings_calendar_window":       "ENRICHER · B6",
    "promoter_pledge_pct":            "NONE_YET · India SAST disclosures",

    # KG
    "kg_community_id":                "PARTIAL · UNKNOWN for backfill dates · HIGH for forward (B5 hook)",
    "kg_community_stability":         "NONE_YET · needs multi-day snapshot delta",
    "kg_community_relative_score":    "PARTIAL · depends on kg_community_id",

    # Cross-runner
    "r1_score":                       "AVAILABLE · from R1 daily output when preserved",
    "r2_score":                       "AVAILABLE · ensemble_score",
    "r3_shadow_score":                "AVAILABLE · r3 shadow ledger (Day 0+)",
    "ensemble_disagreement":          "AVAILABLE · 1 - model_agreement",
    "composite_score":                "AVAILABLE · when composite loop runs",

    # Forward outcome labels (never inputs · labels only)
    "fwd_5d":                         "AVAILABLE · parquet",
    "fwd_10d":                        "AVAILABLE · parquet",
    "fwd_20d":                        "AVAILABLE · parquet",
    "fwd_60d":                        "AVAILABLE · parquet",
    "mfe_in_window":                  "AVAILABLE · derivable",
    "mae_in_window":                  "AVAILABLE · derivable",
    "max_return_in_window":           "AVAILABLE · derivable",
    "eventual_return_in_window":      "AVAILABLE · derivable",
    "time_to_detection_days":         "AVAILABLE · derivable per selection date",
}

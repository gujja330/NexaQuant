"""R3 · Tier-2 research modules · CEO 2026-09-03 PDF R3 Tier-2.

Per V2 §21: each Tier-2 technique = its own Research Ticket with
gate BLOCKED-EVIDENCE until Phase-3 shadow provides justifying evidence.

Techniques (one module each · scaffold + gate + hook):
  stacking                · P_stacked = sigmoid(w1·P_gbm + w2·P_r2 + w3·P_kg + b)
  bayesian_averaging      · Bayesian Model Averaging
  factor_neutral          · size/value/momentum residual scoring
  promoter_governance     · India-specific · pledge + related-party + PSU-tag
  transcript_tone         · prepared remarks + Q&A SEPARATE
  multi_horizon_consensus · fuse forecasts across 5/10/20/60d horizons

All modules follow the same interface:

    from backend.research.r3.tier2.<name> import RESEARCH_TICKET, evaluate

    ticket = RESEARCH_TICKET          # metadata dict
    result = evaluate(root, market)   # returns dict with gate status
"""

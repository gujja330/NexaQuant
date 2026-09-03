"""V2 Phase H · Paper Comparator.

Tracks daily side-by-side:
  R2 production
  candidate strategy (any research strategy that clears backtest gates)
  standing comparator (equal-weight top-10 3-mo momentum · monthly rebal)

Emits reports/research/paper_comparator/{market}.jsonl · one line per date.

No production change. Read-only reporting of what each strategy would have
done today. Used for sustained forward evidence before promotion.
"""
from backend.research.paper_comparator.daily_tick import record_daily_tick

__all__ = ["record_daily_tick"]

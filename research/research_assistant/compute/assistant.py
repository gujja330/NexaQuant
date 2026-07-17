"""DEV026 main Q&A router.

Answers structured queries by dispatching to lib/templates.py. No LLM — every
answer is deterministic and traceable to the underlying JSON reports.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


# ── Public query interface ──────────────────────────────────────────────────

def answer(state, query_type: str, **kwargs) -> dict:
    """Route a structured query to the appropriate template."""
    from research_assistant.lib import templates

    if query_type == "explain_stock":
        return _wrap(templates.explain_stock(state, kwargs["ticker"]), query_type)
    if query_type == "compare":
        return _wrap(templates.compare_stocks(state, kwargs["ticker_a"], kwargs["ticker_b"]),
                     query_type)
    if query_type == "sector_report":
        return _wrap(templates.explain_sector(state, kwargs["sector"]), query_type)
    if query_type == "portfolio_report":
        return _wrap(templates.portfolio_report(state), query_type)
    if query_type == "executive_summary":
        return _wrap(templates.executive_summary(state), query_type)
    if query_type == "investment_memo":
        return _wrap(templates.investment_memo(state, kwargs["ticker"]), query_type)
    return {"status": "unknown_query", "query_type": query_type}


def _wrap(payload: dict, query_type: str) -> dict:
    return {
        "dev_version": "DEV026 v0.1",
        "generated_utc": _now(),
        "code_sha": _git_sha(),
        "query_type": query_type,
        "governance": "Deterministic. Grounded in reports/*.json. Not an LLM.",
        "answer": payload,
    }

"""Research Ticket · one per candidate idea.

Every candidate — a rec engine, a risk overlay, a factor, a sizing rule —
gets ONE JSON ticket at `research/tickets/{ID}.json` that tracks its
lifecycle state end-to-end:

    OPEN → HISTORICAL_BACKTEST → PAPER_PORTFOLIO → LIVE_60D →
    VALIDATED_90D → CEO_REVIEW → {PRODUCTION | REJECTED | DEFERRED}

The ticket is the SINGLE source of truth for a candidate's status.
Telegram, dashboards, and the Research Platform SSoT all read it.

Article IX (Research Lifecycle) freezes this in the constitution:
    no shortcuts, ever · every state transition requires evidence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

LIFECYCLE_STATES = [
    "OPEN",
    "HISTORICAL_BACKTEST",
    "PAPER_PORTFOLIO",
    "LIVE_60D",
    "VALIDATED_90D",
    "CEO_REVIEW",
    "PRODUCTION",
    "REJECTED",
    "DEFERRED",
]


@dataclass
class ResearchTicket:
    ticket_id: str
    title: str
    hypothesis: str
    owner: str = "AEGIS"
    market_scope: str = "india"            # india · usa · both
    mode: str = "delivery"                 # delivery · intraday · risk · sizing · overlay
    lifecycle_state: str = "OPEN"
    opened_at: str = ""
    updated_at: str = ""
    live_experiment_start: str = ""        # first day of paper-portfolio tracking
    days_live: int = 0
    canonical_candidate: bool = False       # true when it's a production-runner candidate
    evidence: dict = field(default_factory=dict)  # references to backtest / metrics files
    decisions: list = field(default_factory=list)  # CEO decisions with timestamps
    tags: list = field(default_factory=list)


def _tickets_dir(root: Path) -> Path:
    d = root / "research" / "tickets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_ticket(root: Path, ticket: ResearchTicket) -> Path:
    """Write ticket to research/tickets/{ID}.json. Stamps updated_at."""
    ticket.updated_at = datetime.now(timezone.utc).isoformat()
    if not ticket.opened_at:
        ticket.opened_at = ticket.updated_at
    p = _tickets_dir(root) / f"{ticket.ticket_id}.json"
    p.write_text(json.dumps(asdict(ticket), indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return p


def load_ticket(root: Path, ticket_id: str) -> ResearchTicket | None:
    p = _tickets_dir(root) / f"{ticket_id}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return ResearchTicket(**data)
    except Exception:
        return None


def load_all_tickets(root: Path) -> list[ResearchTicket]:
    out = []
    for p in _tickets_dir(root).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(ResearchTicket(**data))
        except Exception:
            continue
    return sorted(out, key=lambda t: t.ticket_id)


def advance_ticket_state(root: Path, ticket_id: str, new_state: str,
                            note: str = "", evidence_ref: str = "") -> ResearchTicket | None:
    """Advance a ticket's lifecycle_state. Records a decision entry with timestamp.
    Rejects if new_state is not in the canonical list."""
    if new_state not in LIFECYCLE_STATES:
        return None
    t = load_ticket(root, ticket_id)
    if t is None:
        return None
    prior = t.lifecycle_state
    t.lifecycle_state = new_state
    t.decisions.append({
        "at":              datetime.now(timezone.utc).isoformat(),
        "from_state":      prior,
        "to_state":        new_state,
        "note":            note,
        "evidence_ref":    evidence_ref,
    })
    save_ticket(root, t)
    return t


def bootstrap_starter_tickets(root: Path) -> list[ResearchTicket]:
    """Create the initial tickets for the three current candidates.
    Idempotent · won't overwrite existing tickets."""
    starters = [
        ResearchTicket(
            ticket_id="R001_runner1_adaptive_v2",
            title="Runner 1 · adaptive_rec_v2",
            hypothesis="Legacy Runner 1 (adaptive_rec_v2) delivers institutional "
                            "swing performance on India NSE 200 · 1,060 closed trades since 2022.",
            market_scope="india",
            mode="delivery",
            lifecycle_state="LIVE_60D",
            canonical_candidate=True,
            evidence={
                "positions":     "reports/research/runner1/positions.json",
                "history":       "reports/research/runner1/history.jsonl",
                "backtest":      "reports/research/backtest_2y.json",
            },
            tags=["runner", "delivery", "india", "legacy"],
        ),
        ResearchTicket(
            ticket_id="R002_runner2_ensemble_v3",
            title="Runner 2 · Recommendation v3 (11-model ensemble)",
            hypothesis="Runner 2 (v3 canonical engine) improves on Runner 1 via "
                            "ensemble, calibration, regime adjustment, percentile classifier.",
            market_scope="both",
            mode="delivery",
            lifecycle_state="LIVE_60D",
            canonical_candidate=True,
            evidence={
                "positions":     "reports/research/runner2/positions.json",
                "history":       "reports/research/runner2/history.jsonl",
                "backtest":      "reports/research/backtest_2y.json",
            },
            tags=["runner", "delivery", "india", "usa", "v3"],
        ),
        ResearchTicket(
            ticket_id="R003_intraday_shadow_india",
            title="Intraday Shadow · India",
            hypothesis="Intraday flipping of the same picks would produce a "
                            "materially different equity curve vs swing.",
            market_scope="india",
            mode="intraday",
            lifecycle_state="LIVE_60D",
            canonical_candidate=False,          # per CEO: not a product yet
            evidence={
                "runner1_intraday":  "reports/research/runner1_intraday/positions.json",
                "runner2_intraday":  "reports/research/runner2_intraday/positions.json",
                "correlation":       "reports/research/intraday_delivery_correlation.json",
            },
            decisions=[{
                "at":              datetime.now(timezone.utc).isoformat(),
                "from_state":      "OPEN",
                "to_state":        "LIVE_60D",
                "note":            "DEFERRED as a product per CEO · evidence collection continues",
                "evidence_ref":    "correlation pearson=0.004 corpus-wide · sector-scoped pockets exist",
            }],
            tags=["intraday", "shadow", "india", "deferred"],
        ),
    ]
    written = []
    for t in starters:
        p = _tickets_dir(root) / f"{t.ticket_id}.json"
        if p.exists():
            continue          # idempotent · don't clobber prior state
        save_ticket(root, t)
        written.append(t)
    return written

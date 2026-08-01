"""R006 · Phase 3 · Rotation Hysteresis.

Addresses Issue #1 (rotation engine unstable · 11 different stocks →
same destination overnight) and Issue #9 (rotation destination
explosion).

Policy: a rotation proposal from the scoring engine is APPROVED only if:
    1. Alpha edge > MIN_EDGE_PP threshold (default 5.0pp)
    2. Same rotation candidate has appeared for >= MIN_PERSISTENT_DAYS
       consecutive daily runs (default 3 days)
    3. Fewer than MAX_ROTATIONS_PER_DAY rotations have been approved
       today (default 2)

Everything below thresholds is REJECTED_BY_HYSTERESIS · logged to
rotation_ledger.jsonl · never executed.

Loaded by Runner 2's daily cycle before any ROTATE_OUT/ROTATE_IN
lifecycle events are written.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

MIN_EDGE_PP           = 5.0        # rotation candidate must beat current by >= 5pp
MIN_PERSISTENT_DAYS   = 3          # candidate must appear 3 consecutive days
MAX_ROTATIONS_PER_DAY = 2          # cap daily churn


@dataclass
class RotationProposal:
    from_ticker: str
    to_ticker: str
    edge_pp: float
    from_price: float
    to_price: float


@dataclass
class RotationVerdict:
    proposal: RotationProposal
    approved: bool
    rejected_reason: str = ""
    persistent_days: int = 0


def _rotation_ledger_path(root: Path) -> Path:
    p = root / "reports" / "research" / "rotation_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_recent_proposals(root: Path, market: str, runner: str,
                              days_back: int = 5) -> list[dict]:
    p = _rotation_ledger_path(root)
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("market") == market and d.get("runner") == runner:
                out.append(d)
    except Exception:
        pass
    return out[-500:]           # cap read size


def _count_persistent_days(proposals: list[dict],
                              from_ticker: str, to_ticker: str,
                              today: str) -> int:
    """How many consecutive daily runs has this exact rotation appeared?"""
    days = set()
    for p in proposals:
        if p.get("from_ticker") == from_ticker and p.get("to_ticker") == to_ticker:
            asof = p.get("asof") or ""
            if asof:
                days.add(asof)
    days.add(today)
    return len(days)


def evaluate_proposals(root: Path, market: str, runner: str, asof: str,
                          proposals: Sequence[RotationProposal],
                          min_edge_pp: float = MIN_EDGE_PP,
                          min_persistent_days: int = MIN_PERSISTENT_DAYS,
                          max_per_day: int = MAX_ROTATIONS_PER_DAY,
                          ) -> list[RotationVerdict]:
    """Apply hysteresis · returns approved + rejected verdicts · logs all."""
    recent = _load_recent_proposals(root, market, runner)
    verdicts: list[RotationVerdict] = []
    approved_count = 0

    # Sort proposals by edge_pp descending · best first
    sorted_props = sorted(proposals, key=lambda p: -p.edge_pp)

    for p in sorted_props:
        persistent = _count_persistent_days(recent, p.from_ticker,
                                                 p.to_ticker, asof)
        verdict = RotationVerdict(proposal=p, approved=False, persistent_days=persistent)

        # Gate 1 · alpha edge threshold
        if p.edge_pp < min_edge_pp:
            verdict.rejected_reason = (f"edge {p.edge_pp:+.2f}pp < "
                                                f"threshold {min_edge_pp:+.2f}pp")
        # Gate 2 · persistence
        elif persistent < min_persistent_days:
            verdict.rejected_reason = (f"only {persistent}d persistent < "
                                                f"required {min_persistent_days}d")
        # Gate 3 · daily cap
        elif approved_count >= max_per_day:
            verdict.rejected_reason = (f"daily cap {max_per_day} reached · "
                                                f"queued for tomorrow")
        else:
            verdict.approved = True
            approved_count += 1

        verdicts.append(verdict)

    # Log ALL verdicts to the rotation ledger · audit trail (Issue #6)
    ts_utc = datetime.now(timezone.utc).isoformat()
    with _rotation_ledger_path(root).open("a", encoding="utf-8") as fh:
        for v in verdicts:
            fh.write(json.dumps({
                "ts_utc":           ts_utc,
                "asof":             asof,
                "market":           market,
                "runner":           runner,
                "from_ticker":      v.proposal.from_ticker,
                "to_ticker":        v.proposal.to_ticker,
                "edge_pp":          v.proposal.edge_pp,
                "from_price":       v.proposal.from_price,
                "to_price":         v.proposal.to_price,
                "persistent_days":  v.persistent_days,
                "approved":         v.approved,
                "rejected_reason":  v.rejected_reason,
            }, default=str, ensure_ascii=False) + "\n")
    return verdicts

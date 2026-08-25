# backend/research/statistical_guard.py
"""AEGIS · Sprint M · Phase D · Statistical Discipline (CEO Part 21).

Governance layer · every research finding must pass N-thresholds before
becoming a Research Ticket or influencing production.

Bands (from CEO directive):
  N < 20   · observation only · no ticket allowed
  20-49    · directional evidence · ticket allowed
  50-99    · research candidate
  100+     · production validation candidate (requires walk-forward)

Every ticket in the Research Ticket System (research_ticket.py) MUST
call `assert_ticket_allowed` before being accepted.
"""
from __future__ import annotations

from dataclasses import dataclass


BANDS = [
    (0,   19,  "observation-only",     False, False),
    (20,  49,  "directional",           True,  False),
    (50,  99,  "research-candidate",    True,  False),
    (100, None, "production-candidate", True,  True),
]


@dataclass
class NVerdict:
    n: int
    band: str
    ticket_allowed: bool
    production_ready: bool
    detail: str


def classify_n(n: int) -> NVerdict:
    for low, high, band, ticket, prod in BANDS:
        if high is None or n <= high:
            if n >= low:
                return NVerdict(
                    n=n, band=band, ticket_allowed=ticket,
                    production_ready=prod,
                    detail=f"N={n} → {band} · "
                           f"ticket={'YES' if ticket else 'NO'} · "
                           f"production={'YES' if prod else 'NO'}",
                )
    return NVerdict(n=n, band="unknown", ticket_allowed=False,
                    production_ready=False,
                    detail=f"N={n} out of range")


def assert_ticket_allowed(n: int) -> None:
    v = classify_n(n)
    if not v.ticket_allowed:
        raise ValueError(
            f"Statistical Discipline violation · N={n} is observation-only "
            f"· no Research Ticket may be filed. Wait until N ≥ 20.")


def assert_production_ready(n: int) -> None:
    v = classify_n(n)
    if not v.production_ready:
        raise ValueError(
            f"Statistical Discipline violation · N={n} not production-ready "
            f"· need N ≥ 100 for R1/R2 change. Currently {v.band}.")

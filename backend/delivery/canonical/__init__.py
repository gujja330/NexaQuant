"""AEGIS · Canonical Delivery Object Model · CEO 2026-09-01 authorization.

Establishes the single source-of-truth data model that lives between
the trading engines (Registry / snapshot ledger / parquets · LOCKED)
and the presentation layer (XLSX / Telegram · view-only).

## Architectural principle (CEO)

    Canonical Snapshot / Lifecycle Ledger
                ↓
    DELIVERY CONTRACT (this package)
                ↓
    Validator / Reconciler                 XLSX Renderer
                ↓                                ↓
             PASS/FAIL                     Human analysis

The XLSX layer becomes a pure VIEW of the canonical objects. Business
logic (population membership · lifecycle transitions · missing-field
semantics · identity grain) lives in this package · never in the
renderer. If Excel formatting breaks, the underlying canonical data
remains authoritative.

## What lives here

  · `models`  · dataclasses for CanonicalPosition / CanonicalDecision /
                CanonicalExit / CanonicalLineage
  · `emit`    · JSONL serialisation to
                `reports/canonical/{market}_{population}_{YYYY-MM-DD}.jsonl`
  · `resolve` · pure builder functions (Registry + snapshot ledger +
                parquet → canonical objects) · deterministic

## What does NOT live here

  · Trading logic (R1/R2/E1/E2/E3) · LOCKED
  · Registry decision logic · LOCKED
  · Signal generation · LOCKED
  · XLSX rendering · in `scripts/telegram_command_center_send.py`
  · Telegram delivery · in `scripts/telegram_command_center_send.py`
"""
from backend.delivery.canonical.models import (
    CanonicalPosition,
    CanonicalDecision,
    CanonicalExit,
    Population,
    Lifecycle,
    Decision,
)

__all__ = [
    "CanonicalPosition", "CanonicalDecision", "CanonicalExit",
    "Population", "Lifecycle", "Decision",
]

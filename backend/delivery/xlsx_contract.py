# backend/delivery/xlsx_contract.py
"""AEGIS · Delivery Contract · single source of truth for what belongs
in the delivered XLSX.

CEO directive 2026-08-26 verbatim: "The problem is: the system doesn't
currently have one authoritative definition of what the user is supposed
to see. Excel is merely where the inconsistency becomes visible."

This module formalizes the DELIVERY CONTRACT · defines exactly what
must be true of the XLSX before it ships. No more scattered assertions
across the 3,200-line sender monolith.

Architecture (CEO's own diagram):

    Market → Engines → CANONICAL DECISION → POSITION REGISTRY →
    PORTFOLIO STATE MODEL → XLSX CONTRACT → VALIDATOR → PASS/BLOCK →
    DELIVERY

The validator (xlsx_validator.py) reads THIS contract and asserts
every invariant against a built XLSX. Failure blocks the Telegram POST.

Scope · 3 sheets:
  · Portfolio         · investor-facing decisions
  · Exit History (90d) · realized trades
  · AEGIS {market} History · full audit ledger

Invariants are grouped by SEVERITY:
  BLOCK    · workbook cannot ship if this fires
  WARN     · logged but ships (observation-only checks)
  INFO     · surfaced for operator awareness
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


SCHEMA_FINGERPRINT = "aegis.xlsx_contract.v1.20260826"


# ─────────────────────────────────────────────────────────────────
# Sheet-level contracts
# ─────────────────────────────────────────────────────────────────
@dataclass
class SheetContract:
    name: str
    title_row: int                      # row number of title
    title_pattern: str                  # substring that must appear in title
    analysis_rows: list                 # rows reserved for analysis summary
    header_row: int                     # row number of column headers
    required_header_cells: list         # column headers that MUST exist
    first_data_row: int                 # first row where actual data starts
    min_visible_columns: int = 8        # sanity check


PORTFOLIO_CONTRACT = SheetContract(
    name="Portfolio",
    title_row=1,
    title_pattern="AEGIS",
    analysis_rows=[2, 3],
    header_row=5,
    required_header_cells=[
        "Ticker", "🎯 DECISION", "Month", "Runner", "Sector",
        "Entry Date", "Days", "Entry", "Current", "P&L %", "Stop Loss",
    ],
    first_data_row=6,
    min_visible_columns=8,
)

EXIT_HISTORY_CONTRACT = SheetContract(
    name="Exit History (90d)",
    title_row=1,
    title_pattern="EXIT HISTORY",
    analysis_rows=[2, 3],
    header_row=5,
    required_header_cells=[
        "Stock", "Sector", "Month", "Runner",
        "Entry Date", "Exit Date", "Days Held",
        "Entry Price", "Exit Price", "P&L %", "Exit Reason",
    ],
    first_data_row=6,
)


# ─────────────────────────────────────────────────────────────────
# Invariant registry · what MUST be true after build
# ─────────────────────────────────────────────────────────────────
@dataclass
class Invariant:
    code: str                # I1..IN
    name: str                # human-readable
    severity: str            # BLOCK / WARN / INFO
    scope: str               # which sheet(s) this applies to · "*" = all
    detail: str              # what the invariant enforces
    check_fn_name: str       # method name in XlsxValidator


# The invariant registry · every rule the validator enforces.
# Grouped for readability · order doesn't matter.
INVARIANTS: list = [
    # ── LIFECYCLE consistency ──────────────────────────────────
    Invariant(
        code="I1", name="EXIT rows not in ACTIVE section",
        severity="BLOCK", scope="Portfolio",
        detail="No row whose ACTION column starts '🔴 EXIT' can sit "
               "in the green ACTIVE section",
        check_fn_name="check_no_exit_in_active",
    ),
    Invariant(
        code="I2", name="ACTIVE row has no Exit P&L",
        severity="BLOCK", scope="Portfolio",
        detail="ACTIVE-status row must have Exit P&L cell blank",
        check_fn_name="check_active_row_no_exit_pnl",
    ),
    Invariant(
        code="I3", name="EXIT row has no Active P&L",
        severity="BLOCK", scope="Portfolio",
        detail="EXIT-status row must have Current Perf/Active P&L cell blank",
        check_fn_name="check_exit_row_no_active_pnl",
    ),
    Invariant(
        code="I4", name="No duplicate (ticker, runner)",
        severity="BLOCK", scope="Portfolio",
        detail="Same (ticker, runner) pair must not appear twice in ACTIVE",
        check_fn_name="check_no_duplicate_ticker_runner",
    ),
    Invariant(
        code="I5", name="Position ID immutable",
        severity="BLOCK", scope="Registry",
        detail="Same Position ID never reused for different (ticker, runner, date)",
        check_fn_name="check_position_id_immutable",
    ),
    Invariant(
        code="I6", name="No CLOSED position in ACTIVE section",
        severity="BLOCK", scope="Portfolio",
        detail="A ticker with all-CLOSED Registry entries must not appear "
               "in Portfolio ACTIVE rows",
        check_fn_name="check_no_closed_in_active",
    ),
    Invariant(
        code="I7", name="Same Position ID not in Active + Suggested",
        severity="BLOCK", scope="Portfolio",
        detail="A ticker cannot be tagged Runner=SHADOW/MOMENTUM if it's "
               "already Registry-active",
        check_fn_name="check_no_dup_active_and_suggested",
    ),

    # ── P&L correctness ───────────────────────────────────────
    Invariant(
        code="I8", name="Portfolio summary count = canonical INVESTMENT_ACTIVE",
        severity="BLOCK", scope="Portfolio",
        detail="Row 2 'Active: N positions' must equal the CANONICAL "
               "INVESTMENT_ACTIVE population · Registry active PIDs minus "
               "SHADOW/MOMENTUM/SUGGESTED runners minus positions mutated "
               "to EXIT by binding risk signals. This is NOT the same as "
               "raw Registry active count · risk-mutated + stale positions "
               "are legitimately excluded.",
        check_fn_name="check_summary_count_matches_registry",
    ),
    Invariant(
        code="I9", name="No SUGGESTED contributes to P&L",
        severity="BLOCK", scope="Portfolio",
        detail="SUGGESTED / SHADOW / MOMENTUM rows must NOT be counted "
               "in Unrealized P&L average",
        check_fn_name="check_suggested_not_in_pnl",
    ),
    Invariant(
        code="I10", name="Exit P&L formula reconciles",
        severity="WARN", scope="Portfolio",
        detail="For EXIT rows: quoted Exit P&L ≈ (exit - entry) / entry × 100",
        check_fn_name="check_exit_pnl_formula",
    ),

    # ── Data quality ─────────────────────────────────────────
    Invariant(
        code="I11", name="Every ACTIVE row has entry_price",
        severity="BLOCK", scope="Portfolio",
        detail="ACTIVE-status row must have non-empty Entry Price",
        check_fn_name="check_active_has_entry_price",
    ),
    Invariant(
        code="I12", name="Every ACTIVE row has stop",
        severity="WARN", scope="Portfolio",
        detail="ACTIVE-status row should have Stop Loss populated",
        check_fn_name="check_active_has_stop",
    ),
    Invariant(
        code="I13", name="Prices reconcile to parquet within tolerance",
        severity="WARN", scope="Portfolio",
        detail="Quoted Entry Price must be within 0.5% of parquet close "
               "on Entry Date",
        check_fn_name="check_prices_reconcile",
    ),
    Invariant(
        code="I14", name="No stale data silent inclusion",
        severity="BLOCK", scope="Portfolio",
        detail="If ticker's parquet is > 5 cal days stale, row must be "
               "flagged or excluded",
        check_fn_name="check_no_silent_stale",
    ),

    # ── Sheet structure ──────────────────────────────────────
    Invariant(
        code="I15", name="Sheet title matches contract pattern",
        severity="BLOCK", scope="*",
        detail="Sheet title must contain expected substring (AEGIS · EXIT HISTORY etc.)",
        check_fn_name="check_sheet_title",
    ),
    Invariant(
        code="I16", name="Required headers present",
        severity="BLOCK", scope="*",
        detail="All required_header_cells must exist in the header row",
        check_fn_name="check_required_headers",
    ),
    Invariant(
        code="I17", name="Analysis rows populated",
        severity="WARN", scope="Portfolio",
        detail="Rows 2 + 3 must contain non-empty analysis summary text",
        check_fn_name="check_analysis_rows_populated",
    ),
    Invariant(
        code="I18", name="No jargon in operator-facing text",
        severity="BLOCK", scope="Exit History (90d)",
        detail="Exit Reason column must have no '→ TK.NS · Xpp alpha' jargon",
        check_fn_name="check_no_jargon_in_exit_reasons",
    ),

    # ── Conservation (CEO's biggest ask) ─────────────────────
    Invariant(
        code="I19", name="Momentum candidate conservation",
        severity="WARN", scope="Portfolio",
        detail="Every timing_engine BUY/WATCH/REBOUND_WATCH pick must "
               "either appear in Portfolio OR have a recorded rejection reason",
        check_fn_name="check_momentum_conservation",
    ),
    Invariant(
        code="I20", name="Registry-CLOSED tickers appear in Exit History",
        severity="BLOCK", scope="Exit History (90d)",
        detail="Every Registry-CLOSED opportunity within 90d must appear "
               "in Exit History (90d) sheet",
        check_fn_name="check_closed_tickers_in_exit_history",
    ),

    # ── Lock enforcement ─────────────────────────────────────
    Invariant(
        code="I21", name="Lifecycle uses only canonical states",
        severity="BLOCK", scope="*",
        detail="Status column can only be NEW/ACTIVE/ACTIVE+/EXIT (+HOLD legacy). "
               "PROTECT/REVIEW/TRAIL/TAKE_PROFIT NEVER as lifecycle states",
        check_fn_name="check_canonical_states_only",
    ),
    Invariant(
        code="I22", name="No PROTECT/REVIEW/TRAIL as Status values",
        severity="BLOCK", scope="*",
        detail="Forbidden state values must never appear in Status column",
        check_fn_name="check_no_forbidden_states",
    ),
    Invariant(
        code="I23", name="Runner column has canonical values",
        severity="BLOCK", scope="Portfolio",
        detail="Runner column may only contain R1/R2/SHADOW/MOMENTUM. "
               "Country names (INDIA/USA) as Runner values indicate a "
               "column-offset bug in the Portfolio writer.",
        check_fn_name="check_runner_canonical",
    ),
    Invariant(
        code="I24", name="Header active count matches visible rows",
        severity="BLOCK", scope="Portfolio",
        detail="Row 2 'Active: N positions' must equal the number of "
               "visible ACTIVE + RE-ENTRY rows in the Portfolio table. "
               "Discrepancy indicates Row 2 is counting from a different "
               "source of truth than the table itself.",
        check_fn_name="check_header_matches_visible_rows",
    ),
    Invariant(
        code="I25", name="Realized 90d numbers reconcile to Exit History",
        severity="BLOCK", scope="Portfolio",
        detail="Portfolio Row 2 'Realized 90d ± X% (N exits · WR Y%)' "
               "must match Exit History (90d) sheet row count, average P&L "
               "and win rate. If they diverge, two different populations "
               "are being used as source of truth.",
        check_fn_name="check_realized_matches_exit_history",
    ),
]

# Groupings for the validator to iterate
BLOCK_INVARIANTS = [i for i in INVARIANTS if i.severity == "BLOCK"]
WARN_INVARIANTS = [i for i in INVARIANTS if i.severity == "WARN"]
INFO_INVARIANTS = [i for i in INVARIANTS if i.severity == "INFO"]


# ─────────────────────────────────────────────────────────────────
# Forbidden states (LOCK 2 enforcement)
# ─────────────────────────────────────────────────────────────────
CANONICAL_STATES = {"NEW", "ACTIVE", "ACTIVE+", "EXIT", "HOLD",
                    "ROTATED_SAMEDAY", "CLOSED",
                    "BUY", "STRONG BUY", "ADD", "SELL"}
FORBIDDEN_STATES = {"PROTECT", "REVIEW", "TRAIL", "TAKE_PROFIT",
                    "TAKE PROFIT", "TIGHTEN_STOP"}


# ─────────────────────────────────────────────────────────────────
# Convenience registry access
# ─────────────────────────────────────────────────────────────────
def get_sheet_contract(sheet_name: str) -> Optional[SheetContract]:
    if sheet_name == "Portfolio": return PORTFOLIO_CONTRACT
    if sheet_name == "Exit History (90d)": return EXIT_HISTORY_CONTRACT
    return None


def get_invariants_for_sheet(sheet_name: str) -> list:
    return [i for i in INVARIANTS
            if i.scope in ("*", sheet_name)]


def get_blocking_invariants_for_sheet(sheet_name: str) -> list:
    return [i for i in BLOCK_INVARIANTS
            if i.scope in ("*", sheet_name)]

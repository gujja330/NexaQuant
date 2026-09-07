"""AEGIS · R3 Lane B · TIER-1 EXTERNAL INPUT SPECIFICATIONS.

CEO 2026-09-07 · "We should not tell Claude 'Get FII/DII, PCR, short
interest and earnings.' That's too vague. We need to define the feature
mathematically first."

This module is the FEATURE DEFINITION, not the acquisition code. Each
spec fixes exactly what will be stored, at what grain, with which PIT
cutoff, before any collector is written. Acquisition tracks are separately
registered in research_registry.py and are OUTSIDE R3 Sprint 1.

Nothing here is consumed by Tier-1 yet · all four inputs are
`Data-required` in the Coverage Tracker and `NOT_AVAILABLE_AT_ASOF` in
the feature audit. Core R3 validation proceeds on the PIT-ready subset in
parallel, per the three-lane plan.

THE RULE THAT GOVERNS ALL FOUR
------------------------------
    information_public_at <= trade_asof

A value may enter a feature only if it was PUBLIC at the signal
timestamp. Not "belongs to that fiscal period", not "was first published
later and revised". Where a source revises (NSE FII/DII is explicitly
provisional and may be modified), we store the observation with its own
source timestamp and never overwrite history with a revision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NOT_AVAILABLE = "NOT_AVAILABLE_AT_ASOF"


@dataclass(frozen=True)
class InputSpec:
    id: str
    family: str
    market: str                 # india | usa | both
    grain: str                  # what one stored row represents
    raw_fields: tuple           # exactly what we persist from the source
    derived_features: tuple     # the model-facing features
    pit_cutoff: str             # the rule that makes it point-in-time
    source: str
    hazards: tuple = ()         # named traps that would invalidate it
    status: str = "SPEC_ONLY"   # no collector written yet
    notes: str = ""


# ── B1 · FII / DII flows ──────────────────────────────────────────────
FII_DII = InputSpec(
    id="R3-B1-FIIDII",
    family="fii_dii",
    market="india",
    grain="one row per (date) · MARKET level, not per stock",
    raw_fields=("date", "market", "fii_buy", "fii_sell", "fii_net",
                "dii_buy", "dii_sell", "dii_net",
                "source_timestamp", "source_url", "is_provisional"),
    derived_features=("fii_net_1d", "fii_net_5d", "fii_net_20d",
                      "dii_net_1d", "dii_net_5d", "dii_net_20d",
                      "fii_dii_net_flow_z"),
    pit_cutoff=("NSE publishes end-of-day; the row is usable for a trade "
                "dated D only from D+1 onward unless the publication "
                "timestamp is intraday and precedes the signal."),
    source="NSE FII/FPI & DII daily trading activity reports (CSV)",
    hazards=(
        "MARKET-LEVEL ONLY. These are exchange aggregates. Assigning an "
        "aggregate flow to an individual stock would fabricate a "
        "stock-specific signal that does not exist · the feature joins to "
        "every eligible Indian name for that date as a REGIME feature.",
        "NSE states the figures are provisional and may be modified. "
        "Persist each observation with its own source timestamp; never "
        "overwrite an earlier observation with a later revision, or the "
        "history stops being point-in-time.",
    ),
    notes="India only · no USA equivalent is claimed.",
)

# ── B2 · Options put/call ratio ───────────────────────────────────────
OPTIONS_PCR = InputSpec(
    id="R3-B2-PCR",
    family="options_pcr",
    market="both",
    grain="one row per (date, underlying, expiry)",
    raw_fields=("date", "underlying", "expiry", "call_oi", "put_oi",
                "call_volume", "put_volume", "snapshot_timestamp",
                "is_index", "source"),
    derived_features=("pcr_aggregate_1d", "pcr_near_expiry",
                      "pcr_change_1d", "pcr_percentile_60d"),
    pit_cutoff=("Use the OI snapshot taken at or before the signal "
                "timestamp on that date. Never reconstruct a historical "
                "date from today's live option chain."),
    source="NSE F&O option chain (India) · Cboe historical (USA · coverage "
           "of the public archive must be verified per-name first)",
    hazards=(
        "TODAY'S CHAIN IS NOT HISTORY. The live option-chain endpoint "
        "returns the CURRENT chain. Applying it to a past trade date is "
        "the same lookahead that invalidated the fundamentals feature "
        "store · historical OI snapshots are required.",
        "Expiry selection must be explicit: nearest-expiry and aggregate "
        "are different features and must not be blended.",
        "Zero or missing call OI makes PCR undefined · record "
        "NOT_AVAILABLE_AT_ASOF, never divide-by-zero into an extreme.",
        "Equity options and index options are different regimes and must "
        "not be pooled.",
    ),
)

# ── B3 · Short interest · DELIBERATELY SPLIT BY MARKET ────────────────
SHORT_INTEREST_USA = InputSpec(
    id="R3-B3-SHORT-USA",
    family="short_interest",
    market="usa",
    grain="one row per (report_date, ticker)",
    raw_fields=("report_date", "settlement_date", "ticker",
                "short_interest_shares", "float_shares", "avg_daily_volume",
                "publication_timestamp", "source"),
    derived_features=("short_interest_shares", "short_interest_pct_float",
                      "days_to_cover", "change_vs_previous_report"),
    pit_cutoff=("Short interest is a POSITION SNAPSHOT published on a lag. "
                "Usable only from its publication timestamp, never from "
                "its settlement date."),
    source="FINRA consolidated short interest · SEC Form SHO",
    hazards=(
        "FINRA explicitly distinguishes short-interest POSITION data from "
        "daily short-SALE VOLUME. They are different quantities and must "
        "never be used interchangeably.",
        "Bi-monthly publication means the value is stale between reports · "
        "carry it forward only with an explicit as-of age field.",
    ),
)

SHORT_PROXY_INDIA = InputSpec(
    id="R3-B3-SHORT-INDIA",
    family="short_proxy",     # NOTE: deliberately NOT "short_interest"
    market="india",
    grain="one row per (date, ticker or participant class)",
    raw_fields=("date", "ticker", "short_sale_volume", "slb_open_positions",
                "fno_short_oi", "participant_class", "source_timestamp"),
    derived_features=(),      # none promoted until validated as a proxy
    pit_cutoff="End-of-day report · usable D+1 onward.",
    source="NSE short-selling report · SLB · participant-wise F&O OI",
    hazards=(
        "THERE IS NO INDIA EQUIVALENT OF US SECURITY-LEVEL SHORT INTEREST. "
        "Short-sale VOLUME, SLB open positions and F&O short OI are three "
        "different quantities, none of which is short interest.",
        "Naming any of these `short_interest` would create a false "
        "equivalence across markets and silently corrupt any pooled "
        "analysis. They stay registered as SEPARATE candidate proxies and "
        "must each earn their own validation before promotion.",
    ),
    notes=("Until a proxy is validated, India `short_interest_pct` remains "
           "NOT_AVAILABLE_AT_ASOF. That is the correct answer, not a gap "
           "to be filled by substitution."),
)

# ── B4 · Earnings calendar ────────────────────────────────────────────
EARNINGS_CALENDAR = InputSpec(
    id="R3-B4-EARNINGS",
    family="earnings_calendar",
    market="both",
    grain="one row per (ticker, event)",
    raw_fields=("ticker", "event_type", "event_time", "publication_time",
                "fiscal_period", "source", "is_estimated_date"),
    derived_features=("days_to_next_earnings", "days_since_last_earnings",
                      "earnings_window_0_1d", "earnings_window_2_5d"),
    pit_cutoff=("announcement_public_at <= trade_asof. The PIT key is when "
                "the information became PUBLIC · not the fiscal period it "
                "describes, and not a later-corrected date."),
    source="NSE/BSE corporate filings + event calendar (India) · SEC filing "
           "timestamps + issuer events (USA)",
    hazards=(
        "EARNINGS SURPRISE IS A DIFFERENT FEATURE and must not be smuggled "
        "into the calendar family · it depends on the F01-F05 fundamentals "
        "substrate and is therefore excluded from Tier-1 entirely.",
        "Scheduled dates are frequently revised before the event. Store "
        "is_estimated_date and keep the observation history, or a "
        "backtest will silently use a date that was not yet known.",
    ),
)

ALL_SPECS = (FII_DII, OPTIONS_PCR, SHORT_INTEREST_USA, SHORT_PROXY_INDIA,
             EARNINGS_CALENDAR)


def spec(spec_id: str):
    for s in ALL_SPECS:
        if s.id == spec_id:
            return s
    return None


def summary() -> dict:
    return {
        "n_specs": len(ALL_SPECS),
        "all_spec_only": all(s.status == "SPEC_ONLY" for s in ALL_SPECS),
        "families": sorted({s.family for s in ALL_SPECS}),
        "note": ("Definitions only · no collector is written and no Tier-1 "
                 "feature consumes these. Acquisition is Lane B, separately "
                 "registered and outside R3 Sprint 1."),
        "specs": [
            {"id": s.id, "market": s.market, "family": s.family,
             "n_derived": len(s.derived_features), "n_hazards": len(s.hazards)}
            for s in ALL_SPECS
        ],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2))

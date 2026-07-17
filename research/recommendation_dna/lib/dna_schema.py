"""DEV028 DNA record schema.

Every recommendation is stored as an immutable, versioned DNA record. Fields
match DEV023's recommendation output enriched with DEV020/024/025/027 context.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _rec_id(ticker: str, snapshot_utc: str) -> str:
    """Deterministic recommendation id: hash of ticker + snapshot timestamp."""
    key = f"{ticker}|{snapshot_utc}"
    return "REC-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16].upper()


@dataclass
class DNARecord:
    """Immutable recommendation DNA — one row per version per ticker."""
    dna_id: str                              # unique per version
    recommendation_id: str                   # stable across versions of same rec
    version: int
    snapshot_utc: str
    ticker: str

    # Hierarchy
    sector: str | None = None
    industry: str | None = None
    company_score: float | None = None
    sector_score: float | None = None
    industry_score: float | None = None
    global_score: float | None = None

    # Recommendation
    recommendation_type: str | None = None
    action: str | None = None
    confidence: float | None = None
    classification: str | None = None
    composite_decision_score: float | None = None
    conviction_pct: float | None = None

    # Entry / exit
    entry_price: float | None = None
    stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    trailing_stop: float | None = None
    expected_holding_days: int | None = None

    # Portfolio membership
    in_target_portfolios: list = field(default_factory=list)
    portfolio_weight: float | None = None

    # Rationale
    reasons_for: list = field(default_factory=list)
    reasons_against: list = field(default_factory=list)

    # Diagnostics attached (post-outcome only; populated by DEV027)
    outcome_return_pct: float | None = None
    outcome_win: bool | None = None
    outcome_mfe_pct: float | None = None
    outcome_mae_pct: float | None = None
    outcome_exit_reason: str | None = None
    outcome_holding_days: int | None = None
    doctor_categories: list = field(default_factory=list)

    # Provenance
    source_report: str | None = None
    code_sha: str | None = None
    written_at_utc: str = field(default_factory=_now_utc)

    def key(self) -> str:
        """Deterministic content hash — enables idempotent append."""
        payload = f"{self.recommendation_id}|{self.version}|{self.snapshot_utc}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)


def make_record(ticker: str, snapshot_utc: str, version: int = 1,
                 recommendation_id: str | None = None,
                 **kw) -> DNARecord:
    rid = recommendation_id or _rec_id(ticker, snapshot_utc)
    dna_id = "DNA-" + str(uuid.uuid4())[:12].upper()
    return DNARecord(
        dna_id=dna_id, recommendation_id=rid, version=version,
        snapshot_utc=snapshot_utc, ticker=ticker, **kw,
    )

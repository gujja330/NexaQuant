"""ARCH017A canonical entity dataclasses.

Every entity below matches the schema in docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md.
Only the fields we actively use in DEV017 v0.1 are populated; unused fields are typed
but default to None.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def _uuid7() -> str:
    """Time-ordered UUID (approximation of RFC 4122 v7 without external deps)."""
    # 48-bit unix-ms timestamp + 74 random bits + version/variant
    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rand = uuid.uuid4().int & ((1 << 74) - 1)
    n = (ts_ms << 80) | (0x7 << 76) | ((rand >> 64) & 0xFFF) << 64 | (0b10 << 62) | (rand & ((1 << 62) - 1))
    return str(uuid.UUID(int=n & ((1 << 128) - 1)))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class RawObservation:
    """ARCH017A §4 — the immutable ground-layer datapoint."""
    variable_key: str
    asof_utc: str                  # ISO 8601 UTC — when the observation is *about*
    value: float
    unit: str
    source_id: str
    code_sha: str
    observation_id: str = field(default_factory=_uuid7)
    ingested_at_utc: str = field(default_factory=_now_utc_iso)
    source_row: dict = field(default_factory=dict)
    retrieval_url: Optional[str] = None
    checksum: Optional[str] = None
    superseded_by: Optional[str] = None
    superseded_at_utc: Optional[str] = None

    def __post_init__(self):
        if self.checksum is None:
            key = f"{self.variable_key}|{self.asof_utc}|{self.value}|{self.unit}|{self.source_id}"
            self.checksum = "sha256:" + _sha256_hex(key)


@dataclass
class DerivedMetric:
    """ARCH017A §5 — deterministic transformation of RawObservations."""
    metric_key: str
    asof_utc: str
    value: float
    unit: str
    formula_key: str
    formula_version: str
    code_sha: str
    input_observation_ids: list = field(default_factory=list)
    confidence: float = 1.0
    confidence_components: dict = field(default_factory=dict)
    metric_id: str = field(default_factory=_uuid7)
    computed_at_utc: str = field(default_factory=_now_utc_iso)


@dataclass
class NormalizedIndicator:
    """ARCH017A §6 — standardized [0, 100] scale."""
    indicator_key: str
    asof_utc: str
    value_0_100: float               # clamped to [0, 100]
    normalization_method: str
    normalization_version: str
    code_sha: str
    zscore: Optional[float] = None
    raw_metric_ids: list = field(default_factory=list)
    confidence: float = 1.0
    indicator_id: str = field(default_factory=_uuid7)
    computed_at_utc: str = field(default_factory=_now_utc_iso)


@dataclass
class Classification:
    """ARCH017A §7 — discrete label with confidence."""
    key: str                         # e.g. "global_posture"
    asof_utc: str
    label: str                       # from a fixed enum
    confidence: float
    contributing_indicator_ids: list = field(default_factory=list)
    duration_days: int = 0
    previous_label: Optional[str] = None


@dataclass
class CompositeScore:
    """ARCH017A §8 — weighted combination with contribution breakdown."""
    composite_key: str
    asof_utc: str
    value_0_100: float
    classification: str              # matching label
    confidence: float
    weighting_scheme: str
    weighting_version: str
    component_indicators: list = field(default_factory=list)  # list of dicts
    composite_id: str = field(default_factory=_uuid7)
    computed_at_utc: str = field(default_factory=_now_utc_iso)


def as_dict(obj: Any) -> dict:
    """Serialize any dataclass instance to a JSON-safe dict."""
    return json.loads(json.dumps(asdict(obj), default=str))

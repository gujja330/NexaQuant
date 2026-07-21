"""Learning Engine data types — Sprint 6."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class ErrorBucket(str, Enum):
    """Coarse root-cause categorisation of a loss."""
    UNDERESTIMATED_VOL    = "underestimated_vol"
    REGIME_CHANGE         = "regime_change"
    SURPRISE_EARNINGS     = "surprise_earnings"
    LIQUIDITY_SHOCK       = "liquidity_shock"
    SECTOR_ROTATION_MISS  = "sector_rotation_missed"
    WORKED_AS_EXPECTED    = "worked_as_expected"      # for winners
    UNCLASSIFIED          = "unclassified"


@dataclass
class LearningRow:
    """One row per closed-horizon recommendation — the atomic unit of the corpus.

    Natural key: (market, ticker, rec_asof). Append-only on this key.
    """
    market:                str
    ticker:                str
    rec_asof:              date              # date the recommendation was emitted
    horizon_close_date:    date              # date the horizon actually closed
    action:                str               # STRONG_BUY / BUY / SELL / STRONG_SELL
    ensemble_score:        float
    calibrated_confidence: float
    regime_at_rec:         str
    # Outcome
    entry_price:           float | None
    exit_price:            float | None
    return_pct:            float | None      # signed return (positive = winner for BUY)
    is_winner:             bool
    horizon_days:          int
    hit_stop_loss:         bool = False
    hit_take_profit:       bool = False
    # Attribution
    top_models:            list = field(default_factory=list)      # [model_id, ...]
    top_features:          list = field(default_factory=list)
    feature_attribution:   dict = field(default_factory=dict)      # {feature: contribution}
    model_attribution:     dict = field(default_factory=dict)      # {model_id: contribution}
    # Root cause
    error_bucket:          str = ErrorBucket.UNCLASSIFIED.value
    # Provenance
    model_stamp_at_rec:    dict = field(default_factory=dict)
    feature_set_version:   str = ""
    schema_fingerprint:    str = ""


@dataclass
class Attribution:
    """Per-feature or per-model attribution across the corpus."""
    key:               str                 # feature name OR model_id
    n_observations:    int
    avg_contribution:  float               # signed
    winner_frequency:  float               # fraction of times key drove a winner
    loser_frequency:   float
    net_alpha:         float               # winners' avg - losers' avg


@dataclass
class FailureCluster:
    """One cluster of failed recommendations sharing a signature."""
    cluster_id:            int
    n_members:             int
    dominant_features:     dict = field(default_factory=dict)      # feature → mean value
    dominant_error_bucket: str  = ErrorBucket.UNCLASSIFIED.value
    representative_tickers: list = field(default_factory=list)
    recommended_step:      str  = ""                                # non-recommendation phrasing
    silhouette:            float | None = None


@dataclass
class CalibrationCurve:
    """Confidence-to-empirical-winrate mapping.

    bin_edges: sorted list of confidence-bin edges [0, 0.1, 0.2, ..., 1.0]
    win_rates: empirical winner-fraction per bin (parallel to bin_edges[:-1])
    """
    method:            str                 # "identity" | "isotonic" | "platt"
    n_observations:    int
    bin_edges:         list = field(default_factory=list)
    empirical_win_rates: list = field(default_factory=list)
    fitted_win_rates:  list = field(default_factory=list)
    calibration_error: float = 0.0         # RMS(fitted - empirical)

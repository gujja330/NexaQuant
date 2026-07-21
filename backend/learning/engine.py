"""LearningEngine — composes outcome computer + attributions + clustering + calibration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from backend.learning.corpus              import (
    read_corpus, append_corpus, load_recommendation_history,
)
from backend.learning.outcome_computer    import compute_outcomes, DEFAULT_HORIZON_DAYS
from backend.learning.feature_attribution import compute_feature_attribution
from backend.learning.model_attribution   import compute_model_attribution
from backend.learning.failure_clustering  import cluster_failures
from backend.learning.calibration         import fit_calibration_curve
from backend.learning.types               import (
    LearningRow, Attribution, FailureCluster, CalibrationCurve,
)


@dataclass
class LearningEngineResult:
    market:              str
    asof:                date
    engine_version:      str = "v1.0"
    horizon_days:        int = DEFAULT_HORIZON_DAYS
    n_recs_in_history:   int = 0
    n_new_closed:        int = 0
    n_corpus_total:      int = 0
    n_winners:           int = 0
    n_losers:            int = 0
    win_rate:            float | None = None
    avg_return:          float | None = None
    feature_attribution: list = field(default_factory=list)
    model_attribution:   list = field(default_factory=list)
    failure_clusters:    list = field(default_factory=list)
    calibration_curve:   CalibrationCurve | None = None
    notes:               list = field(default_factory=list)


class LearningEngine:
    ENGINE_ID       = "aegis.learning.v1"
    ENGINE_VERSION  = "1.0.0"

    def __init__(self, repo_root: Path, market: str,
                    horizon_days: int = DEFAULT_HORIZON_DAYS,
                    min_cluster_size: int = 3,
                    n_calibration_bins: int = 10,
                    schema_fingerprint: str = "",
                    feature_set_version: str = ""):
        self.repo_root = Path(repo_root)
        self.market = market
        self.horizon_days = horizon_days
        self.min_cluster_size = min_cluster_size
        self.n_calibration_bins = n_calibration_bins
        self.schema_fingerprint = schema_fingerprint
        self.feature_set_version = feature_set_version

    def run(self, asof: date | None = None) -> LearningEngineResult:
        asof = asof or date.today()
        result = LearningEngineResult(market=self.market, asof=asof,
                                          horizon_days=self.horizon_days)

        # 1) Load prior corpus + recommendation history
        corpus = read_corpus(self.repo_root, self.market)
        history = load_recommendation_history(self.repo_root, self.market)
        result.n_recs_in_history = int(len(history))

        # 2) Compute outcomes for newly-closed horizons
        already_closed = set()
        if not corpus.empty and {"market", "ticker", "rec_asof"}.issubset(corpus.columns):
            already_closed = set(zip(
                corpus["market"].astype(str),
                corpus["ticker"].astype(str),
                corpus["rec_asof"].astype(str),
            ))

        new_rows = compute_outcomes(
            self.repo_root, self.market, history,
            cutoff=asof, horizon_days=self.horizon_days,
            already_closed_keys=already_closed,
        )
        # 3) Append to corpus
        _, n_added = append_corpus(self.repo_root, self.market, new_rows)
        result.n_new_closed = n_added

        # 4) Re-load corpus for downstream analysis
        corpus = read_corpus(self.repo_root, self.market)
        result.n_corpus_total = int(len(corpus))
        if not corpus.empty and "is_winner" in corpus.columns:
            wins = corpus[corpus["is_winner"].astype(bool)]
            losers = corpus[~corpus["is_winner"].astype(bool)]
            result.n_winners = int(len(wins))
            result.n_losers = int(len(losers))
            if len(corpus) > 0:
                result.win_rate = round(len(wins) / len(corpus), 4)
            if "return_pct" in corpus.columns and len(corpus):
                result.avg_return = round(float(corpus["return_pct"].mean()), 6)

        # 5) Attributions
        result.feature_attribution = compute_feature_attribution(corpus)
        result.model_attribution = compute_model_attribution(corpus)

        # 6) Failure clustering
        result.failure_clusters = cluster_failures(corpus, self.min_cluster_size)

        # 7) Calibration curve
        result.calibration_curve = fit_calibration_curve(corpus, self.n_calibration_bins)

        # Notes
        if result.n_corpus_total == 0:
            result.notes.append("learning corpus is EMPTY — no horizons have closed yet. "
                                "This is honest, not broken. Corpus populates as recommendations "
                                "close their 60-day horizons OR as Sprint 8 walk-forward runs "
                                "generate historical closes.")
        elif result.n_corpus_total < 30:
            result.notes.append(f"learning corpus has only {result.n_corpus_total} rows — "
                                "attributions and clustering are directional but not statistically robust yet.")
        else:
            result.notes.append(f"learning corpus has {result.n_corpus_total} rows across "
                                f"{result.n_winners} winners + {result.n_losers} losers.")
        result.notes.append(f"calibration method: {result.calibration_curve.method} "
                            f"(n_observations={result.calibration_curve.n_observations})")
        return result

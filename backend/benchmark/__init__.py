"""
Sprint 7.8 · Recommendation Benchmark Report.

Comprehensive metric panel over any runner's closed-position corpus, with
explicit statistical-significance gates so a small-sample "PASS" verdict
can never masquerade as institutional evidence.

Consumes:
    reports/learning_corpus.parquet           (Runner 2 · Rec Engine v3)
    reports/learning_corpus_runner1.parquet   (Runner 1 · legacy audit ledger)

Produces:
    reports/benchmark_<runner>_<market>.json  (full metric panel)
    reports/benchmark_compare.json            (side-by-side runner ranking, only when both have ≥30 closed)

Design principles:
- Every metric carries a sample size and — where meaningful — a 95% confidence
  interval or a p-value flag. Nothing gets reported without its uncertainty.
- Verdicts are structural (INSUFFICIENT_DATA → DIRECTIONAL → INSTITUTIONAL),
  never "GOOD" / "BAD" — the operator interprets, the module measures.
- Read-only over history parquets; never mutates the corpus.
- Free-stack: pandas + numpy only.
"""
from .report import (
    build_benchmark_report,
    build_comparison,
    BenchmarkReport,
    BenchmarkMetrics,
    StatisticalVerdict,
    SIGNIFICANCE_MIN_SAMPLES,
    INSTITUTIONAL_MIN_SAMPLES,
)
from .statistical_significance import (
    wilson_confidence_interval,
    mean_confidence_interval,
    sample_size_verdict,
)

ENGINE_ID = "aegis.benchmark.v1"
ENGINE_VERSION = "1.0.0"

__all__ = [
    "build_benchmark_report", "build_comparison",
    "BenchmarkReport", "BenchmarkMetrics", "StatisticalVerdict",
    "SIGNIFICANCE_MIN_SAMPLES", "INSTITUTIONAL_MIN_SAMPLES",
    "wilson_confidence_interval", "mean_confidence_interval", "sample_size_verdict",
    "ENGINE_ID", "ENGINE_VERSION",
]

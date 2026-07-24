"""Sprint B0 · History Quality Engine · orchestrator."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .types import (
    FamilyStatus, FamilyCheckResult, QualityReport, ReadinessVerdict,
)
from .validators import (
    check_history_parquet, check_learning_corpus, check_price_universe,
)
from .metrics import aggregate_score


ENGINE_ID = "aegis.history_quality.v1"
ENGINE_VERSION = "1.0.0"


# Family manifest — the 10 history sources every market has (or should have) per Sprint 7.5+.
# Each tuple = (family_name, path_template)
# Family manifest — each entry: (family_name, path_template, extra_dedupe_keys).
# Most families are per-day snapshots keyed on (market, asof). Factor library is
# multi-row-per-day: one row per (market, asof, factor).
FAMILIES = [
    ("recommendation",           "{reports}/recommendation_history.parquet",           ()),
    ("recommendation_runner1",   "{reports}/recommendation_history_runner1.parquet",   ()),
    ("risk",                     "{reports}/risk_history.parquet",                     ()),
    ("portfolio",                "{reports}/portfolio_history.parquet",                ()),
    ("execution",                "{reports}/execution_history.parquet",                ()),
    ("learning",                 "{reports}/learning_history.parquet",                 ()),
    ("macro",                    "{reports}/macro_history.parquet",                    ()),
    ("factor_library",           "{reports}/factor_library_history.parquet",           ("factor",)),
]


class HistoryQualityEngine:
    """Runs all family checks for a market and produces a QualityReport."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def market_reports(self, market: str) -> Path:
        return (self.repo_root / "reports") if market == "india" \
            else (self.repo_root / "usa" / "reports")

    def market_raw(self, market: str) -> Path:
        return (self.repo_root / "data" / "raw" / "india") if market == "india" \
            else (self.repo_root / "usa" / "data" / "raw" / "us")

    def _run_history_families(self, market: str) -> List[FamilyCheckResult]:
        reports = self.market_reports(market)
        results: List[FamilyCheckResult] = []
        for family, template, extra_dedupe_keys in FAMILIES:
            path = Path(template.format(reports=str(reports)))
            results.append(check_history_parquet(
                family=family, path=path, market=market,
                extra_dedupe_keys=extra_dedupe_keys,
            ))
        # Learning corpus (different key from history)
        results.append(check_learning_corpus(
            path=reports / "learning_corpus.parquet", market=market,
        ))
        # Also check runner1-specific learning corpus if present
        if (reports / "learning_corpus_runner1.parquet").exists():
            r = check_learning_corpus(
                path=reports / "learning_corpus_runner1.parquet", market=market,
            )
            # rename to disambiguate
            results.append(FamilyCheckResult(
                family="learning_corpus_runner1",
                file_path=r.file_path, exists=r.exists,
                status=r.status, n_rows=r.n_rows,
                schema_ok=r.schema_ok, schema_issues=r.schema_issues,
                quality_score=r.quality_score, notes=r.notes,
            ))
        return results

    def _run_price_universe(self, market: str) -> FamilyCheckResult:
        return check_price_universe(
            raw_dir=self.market_raw(market), market=market,
            required_min_tickers=(30 if market == "usa" else 100),
        )

    def _readiness_verdict(self, results: List[FamilyCheckResult]) -> str:
        n_fail = sum(1 for r in results if r.status == FamilyStatus.FAIL.value)
        n_warn = sum(1 for r in results if r.status == FamilyStatus.WARN.value)
        # Critical-family failures gate B1 replay:
        critical = {"price", "recommendation"}
        critical_fail = any(
            r.status == FamilyStatus.FAIL.value and r.family in critical
            for r in results
        )
        if critical_fail:
            return ReadinessVerdict.NEEDS_REPAIR.value
        if n_fail > 0:
            return ReadinessVerdict.NEEDS_REPAIR.value
        if n_warn > 2:
            return ReadinessVerdict.PARTIAL.value
        # If price universe passes AND rec+macro exist (even WARN), we can replay
        return ReadinessVerdict.READY_FOR_REPLAY.value

    def run(self, market: str) -> QualityReport:
        history_results = self._run_history_families(market)
        price_result = self._run_price_universe(market)

        all_results = history_results + [price_result]

        n_pass = sum(1 for r in all_results if r.status == FamilyStatus.PASS.value)
        n_warn = sum(1 for r in all_results if r.status == FamilyStatus.WARN.value)
        n_fail = sum(1 for r in all_results if r.status == FamilyStatus.FAIL.value)
        n_na   = sum(1 for r in all_results if r.status == FamilyStatus.NOT_APPLICABLE.value)

        overall = aggregate_score([r.quality_score for r in all_results])
        verdict = self._readiness_verdict(all_results)

        # Corporate-action flags surfaced from price-universe stalled tickers
        ca_flags: List[Dict[str, Any]] = []
        for note in (price_result.notes or []):
            if "stalled" in note.lower():
                ca_flags.append({"family": "price", "signal": note})

        notes: List[str] = []
        if verdict == ReadinessVerdict.NEEDS_REPAIR.value:
            fails = [r.family for r in all_results if r.status == FamilyStatus.FAIL.value]
            notes.append(f"NEEDS_REPAIR — critical family failures: {fails}")
        elif verdict == ReadinessVerdict.PARTIAL.value:
            notes.append(f"PARTIAL — {n_warn} warnings; can proceed to B1 with reduced coverage")
        else:
            notes.append("READY_FOR_REPLAY — proceed to Sprint B1")

        return QualityReport(
            engine=ENGINE_ID, version=ENGINE_VERSION,
            market=market,
            run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            verdict=verdict,
            n_families_checked=len(all_results),
            n_pass=n_pass, n_warn=n_warn, n_fail=n_fail, n_not_applicable=n_na,
            overall_quality_score=overall,
            per_family=all_results,
            corporate_action_flags=ca_flags,
            notes=notes,
        )


def run_quality_check(*, repo_root: Path, market: str) -> QualityReport:
    return HistoryQualityEngine(repo_root).run(market)

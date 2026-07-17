"""DEV028 ingest engine.

Reads DEV023 recommendations + DEV020 company context + optional DEV024/025/027
enrichment, produces DNA records, and appends to the immutable store.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from recommendation_dna.lib import dna_schema, store, versioning                     # noqa: E402


REPORTS_DIR = _ROOT / "reports"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.load(path.open("r", encoding="utf-8"))
    except Exception:
        return None


def ingest_current_recommendations() -> tuple[int, int]:
    """Read reports/recommendations.json + reports/company_context.json,
    build DNA records for every rec, apply versioning, append to store."""
    recs_bundle = _load(REPORTS_DIR / "recommendations.json")
    if not recs_bundle:
        return 0, 0

    company_ctx = _load(REPORTS_DIR / "company_context.json") or {}
    company_lookup = {c["ticker"]: c for c in company_ctx.get("companies", [])
                        if c.get("status") == "computed"}

    snapshot_utc = recs_bundle.get("run_utc") or datetime.now(timezone.utc).isoformat() + "Z"
    code_sha = _git_sha()

    records: list[dna_schema.DNARecord] = []
    for r in recs_bundle.get("recommendations", []):
        ticker = r["ticker"]
        ee = r.get("entry_exit") or {}
        cc = company_lookup.get(ticker, {})
        hierarchy = cc.get("hierarchy", {})

        # Check versioning
        prev = store.latest_by_ticker(ticker)
        this_record = {
            "recommendation_type":       r.get("recommendation"),
            "action":                    r.get("action"),
            "classification":            r.get("classification"),
            "target_1":                  ee.get("target_1"),
            "target_2":                  ee.get("target_2"),
            "stop_loss":                 ee.get("stop_loss"),
            "trailing_stop":             ee.get("trailing_stop_initial"),
        }
        changed, changed_fields = versioning.has_changed(prev, this_record)
        if not changed and prev is not None:
            continue                                             # no update needed

        version = versioning.next_version(prev)

        # Stable recommendation_id: keep parent's if we're incrementing version
        recommendation_id = prev.get("recommendation_id") if prev else None

        rec = dna_schema.make_record(
            ticker=ticker, snapshot_utc=snapshot_utc, version=version,
            recommendation_id=recommendation_id,
            sector=r.get("sector"),
            industry=r.get("industry"),
            company_score=r.get("score"),
            sector_score=r.get("sector_score"),
            industry_score=r.get("industry_score"),
            global_score=r.get("global_score"),
            recommendation_type=r.get("recommendation"),
            action=r.get("action"),
            confidence=r.get("confidence"),
            classification=r.get("classification"),
            composite_decision_score=r.get("composite_decision_score"),
            conviction_pct=r.get("conviction_pct"),
            entry_price=ee.get("latest_close"),
            stop_loss=ee.get("stop_loss"),
            target_1=ee.get("target_1"),
            target_2=ee.get("target_2"),
            trailing_stop=ee.get("trailing_stop_initial"),
            expected_holding_days=ee.get("expected_holding_days"),
            in_target_portfolios=r.get("in_target_portfolios", []),
            portfolio_weight=r.get("current_weight"),
            reasons_for=r.get("reasons_for", []),
            reasons_against=r.get("reasons_against", []),
            source_report="recommendations.json",
            code_sha=code_sha,
        )
        records.append(rec)

    return store.append(records)


def ingest_outcomes_from_learning() -> int:
    """After DEV025 has computed outcomes, enrich existing DNA records.

    v0.1: since outcomes come from historical walk-forward (not live),
    we don't back-annotate existing records — the outcome-linkage flow is a
    v0.2 responsibility (needs live position tracking + broker fills).
    """
    return 0


def run(verbose: bool = True) -> dict:
    added, deduped = ingest_current_recommendations()
    outcomes_enriched = ingest_outcomes_from_learning()

    if verbose:
        print(f"  records added:   {added}")
        print(f"  records deduped: {deduped}")
        print(f"  outcomes bound:  {outcomes_enriched}")

    from recommendation_dna.lib import search
    stats = search.statistics()

    return {
        "run_utc":          datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":         _git_sha(),
        "dev_version":      "DEV028 v0.1",
        "records_added":    added,
        "records_deduped":  deduped,
        "outcomes_bound":   outcomes_enriched,
        "corpus_statistics": stats,
    }

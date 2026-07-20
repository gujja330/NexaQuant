"""AI Data Quality Agent v1.0.

Reads backend_validation summary + canonical dataset counts + freshness
history. Explains data health in prose, flags anomalies, and highlights
the most consequential gaps.

**Does NOT compute new numbers.** Every claim is grounded in a Sprint 1
validator output — this agent is the narrator, not the auditor.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.ai.base import AgentOutput

VERSION = "v1.0"


def run(repo_root: Path, market_name: str,
         asof: date | None = None) -> AgentOutput:
    root = Path(repo_root)
    if market_name == "usa":
        summary_path = root / "usa" / "reports" / "backend_validation_summary.json"
    else:
        summary_path = root / "reports" / "backend_validation_summary.json"

    findings: list[dict] = []
    citations: list[str] = [str(summary_path.relative_to(root).as_posix())]
    evidence: dict = {}
    caveats: list[str] = []

    if not summary_path.exists():
        return AgentOutput(
            agent="data_quality", version=VERSION, market=market_name,
            asof=asof or date.today(),
            headline="No backend validation summary found",
            narrative=("Backend validation has not run for this market yet. "
                        "Run `python {}/backend_validation/run.py` to generate the summary.")
                       .format(market_name),
            confidence=0.0,
            caveats=["Missing input — narrative is a stub"],
        )

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    verdict = data.get("verdict", "UNKNOWN")
    conf = float(data.get("confidence", 0.0))
    counts = data.get("counts", {})
    top_issues = data.get("top_issues", [])[:5]
    n_datasets = int(data.get("n_datasets", 0))

    evidence = {
        "n_datasets": n_datasets, "verdict": verdict, "confidence": conf,
        "counts": counts, "n_top_issues": len(top_issues),
    }

    # ── Narrative construction (deterministic templates) ────────
    verdict_line = {
        "PASS":      f"All {n_datasets} registered datasets are within their SLAs.",
        "WARNING":   f"Backend health is DEGRADED — {counts.get('WARNING', 0)} dataset(s) crossed warning thresholds.",
        "FAIL":      f"Backend health is CRITICAL — {counts.get('FAIL', 0)} dataset(s) failed their SLA.",
        "UNKNOWN":   "Backend validation returned an unrecognised verdict.",
    }.get(verdict, "Backend validation state unclear.")

    conf_line = f"Composite confidence is {conf:.3f} (weighted geometric mean across " \
                "freshness · schema · completeness · quality · lineage)."

    if top_issues:
        issue_lines = []
        for i, iss in enumerate(top_issues, 1):
            findings.append({
                "rank": i, "severity": iss.get("severity", "?"),
                "dataset": iss.get("dataset", "?"),
                "validator": iss.get("validator", "?"),
                "message": iss.get("message", ""),
            })
            issue_lines.append(f"  {i}. [{iss.get('severity', '?')}] "
                                f"{iss.get('dataset', '?')} · "
                                f"{iss.get('validator', '?')} · "
                                f"{iss.get('message', '')}")
        issues_narrative = "Top issues to look at:\n" + "\n".join(issue_lines)
    else:
        issues_narrative = "No dataset issues flagged."

    # Concrete follow-up steer
    if verdict == "FAIL":
        followup = ("Recommended: pause downstream inference for any engine that depends on "
                     "a failed dataset, or explicitly acknowledge stale-data risk in the "
                     "recommendation output.")
    elif verdict == "WARNING":
        followup = ("Recommended: schedule the affected ingestion module to run again "
                     "and re-check before the next orchestrator cycle.")
    else:
        followup = "No immediate action required. Continue normal cadence."

    narrative = "\n\n".join([verdict_line, conf_line, issues_narrative, followup])

    return AgentOutput(
        agent="data_quality", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=verdict_line,
        narrative=narrative,
        findings=findings,
        evidence=evidence,
        citations=citations,
        confidence=conf,
        caveats=caveats,
        determinism="template",
    )

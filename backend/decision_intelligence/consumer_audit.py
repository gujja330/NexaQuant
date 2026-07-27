"""End-to-End Consumer Audit.

Traces every artifact from producer (orchestrator step) → consumer
(orchestrator step + Python module + dashboard + Telegram sender). Detects:

    orphan_report      : produced by orchestrator, no consumer
    broken_chain       : required by orchestrator, no producer
    report_only        : consumed only by dashboard/report/telegram (no engine)
    unused_by_engines  : never influences a downstream engine decision
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.decision_intelligence.consumer_audit.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.decision_intelligence.consumer_audit.v1"


@dataclass
class ArtifactRecord:
    artifact: str
    producers: list[str] = field(default_factory=list)   # orchestrator step names
    consumers: list[str] = field(default_factory=list)   # orchestrator step names
    py_references: list[str] = field(default_factory=list)   # file paths
    classification: str = ""    # HEALTHY · ORPHAN_REPORT · BROKEN_CHAIN · REPORT_ONLY


@dataclass
class ConsumerAuditReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    n_artifacts: int = 0
    n_healthy: int = 0
    n_orphan_report: int = 0
    n_broken_chain: int = 0
    n_report_only: int = 0
    n_decision_influencing: int = 0
    per_artifact: list[dict] = field(default_factory=list)
    broken_chain_details: list[dict] = field(default_factory=list)
    orphan_report_details: list[dict] = field(default_factory=list)


# Artifacts consumed by engines (not just dashboards/reports/Telegram) →
# these actually INFLUENCE decisions.
_ENGINE_CONSUMER_MODULES = (
    "backend/recommendation", "backend/risk", "backend/portfolio",
    "backend/model_factory", "backend/learning", "backend/replay",
    "backend/benchmark", "backend/macro_intel", "backend/factor_library",
    "backend/decision_intelligence",
    "india/recommendation_intelligence", "india/risk_engine",
    "india/portfolio_engine", "india/learning_engine",
    "usa/research/",
    "research/adaptive_rec_v2", "research/risk_capital_v2",
    "research/fusion", "research/knowledge_graph",
    "research/institutional_memory", "research/decision_center",
)

_REPORT_ONLY_MODULES = (
    "scripts/telegram_send", "scripts/aegis_ops_check",
    "scripts/aegis_health_check", "ux/dashboard", "ux/telegram",
    "research/morning_report", "india/aegis_dashboard",
)


def _parse_orchestrator(root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (produces_map, requires_map): step_name → [artifact paths]."""
    produces: dict[str, list[str]] = {}
    requires: dict[str, list[str]] = {}
    for path in [root / "scripts" / "aegis_daily_v2.py",
                  root / "usa" / "scripts" / "usa_daily.py"]:
        if not path.exists(): continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception: continue
        # Find each { "name": "X", ... "produces": [...], "requires": [...] } block
        for m in re.finditer(r'"name":\s*"([\w_]+)"([^{}]|\{[^{}]*\})*?"produces":\s*\[([^\]]*)\]', text):
            name = m.group(1)
            prods_str = m.group(3)
            arts = re.findall(r'"([\w./\-]+)"', prods_str)
            produces.setdefault(name, []).extend(arts)
        for m in re.finditer(r'"name":\s*"([\w_]+)"([^{}]|\{[^{}]*\})*?"requires":\s*\[([^\]]*)\]', text):
            name = m.group(1)
            reqs_str = m.group(3)
            arts = re.findall(r'"([\w./\-]+)"', reqs_str)
            requires.setdefault(name, []).extend(arts)
    return produces, requires


def _find_py_references(root: Path, artifact_basename: str) -> list[str]:
    """Which .py files mention this artifact filename?"""
    hits = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts or "archive" in p.parts: continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception: continue
        if artifact_basename in text:
            hits.append(str(p.relative_to(root)))
    return hits


def _classify(rec: ArtifactRecord) -> str:
    """Assign classification per consumer analysis."""
    if not rec.producers and rec.consumers:
        return "BROKEN_CHAIN"   # required but not produced
    if rec.producers and not rec.consumers and not rec.py_references:
        return "ORPHAN_REPORT"
    engine_consumers = [r for r in rec.py_references
                          if any(r.startswith(m) for m in _ENGINE_CONSUMER_MODULES)]
    report_only_consumers = [r for r in rec.py_references
                              if any(r.startswith(m) for m in _REPORT_ONLY_MODULES)]
    if not engine_consumers and report_only_consumers:
        return "REPORT_ONLY"
    if engine_consumers:
        return "HEALTHY"
    return "REPORT_ONLY"


class ConsumerAuditEngine:

    def __init__(self, root: Path):
        self.root = Path(root)

    def run(self) -> ConsumerAuditReport:
        produces, requires = _parse_orchestrator(self.root)
        # Build artifact index: artifact_path → producers/consumers
        artifacts: dict[str, ArtifactRecord] = {}
        for step, arts in produces.items():
            for a in arts:
                rec = artifacts.setdefault(a, ArtifactRecord(artifact=a))
                if step not in rec.producers:
                    rec.producers.append(step)
        for step, arts in requires.items():
            for a in arts:
                rec = artifacts.setdefault(a, ArtifactRecord(artifact=a))
                if step not in rec.consumers:
                    rec.consumers.append(step)

        # Add py-reference for each artifact
        for a, rec in artifacts.items():
            basename = Path(a).name
            refs = _find_py_references(self.root, basename)
            # Exclude orchestrator scripts themselves (would tautologically match)
            refs = [r for r in refs if not r.endswith("aegis_daily_v2.py")
                    and not r.endswith("usa_daily.py")]
            rec.py_references = refs
            rec.classification = _classify(rec)

        rep = ConsumerAuditReport(run_utc=datetime.now(timezone.utc).isoformat())
        rep.n_artifacts = len(artifacts)
        for rec in artifacts.values():
            cls = rec.classification
            if cls == "HEALTHY":
                rep.n_healthy += 1
                rep.n_decision_influencing += 1
            elif cls == "ORPHAN_REPORT":
                rep.n_orphan_report += 1
                rep.orphan_report_details.append({
                    "artifact": rec.artifact, "producers": rec.producers})
            elif cls == "BROKEN_CHAIN":
                rep.n_broken_chain += 1
                rep.broken_chain_details.append({
                    "artifact": rec.artifact, "consumers": rec.consumers})
            elif cls == "REPORT_ONLY":
                rep.n_report_only += 1
            rep.per_artifact.append(asdict(rec))
        return rep


def run_consumer_audit(root: Path) -> dict:
    return asdict(ConsumerAuditEngine(root).run())

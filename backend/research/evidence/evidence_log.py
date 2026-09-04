"""Section M · Immutable append-only Evidence Log.

Every run creates ONE record · never overwrites. Reruns get new experiment_id.
Path · reports/research/evidence/evidence_log.jsonl
"""
from __future__ import annotations
import json
import os
import uuid
from datetime import datetime
from pathlib import Path


def _git_commit(root: Path) -> str:
    try:
        head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:].strip()
            sha = (root / ".git" / ref).read_text(encoding="utf-8").strip()
            return sha[:12]
        return head[:12]
    except Exception:
        return "unknown"


def append_evidence_record(root: Path, *,
                            item_id: str, market: str,
                            data_snapshot: str, pit_status: str,
                            fold_definition: dict, trial_count: int,
                            parameters: dict, sample_size: int,
                            metrics: dict, statistical_test: dict,
                            multiple_testing_correction: dict, decision: str,
                            artifact_paths: list[str]) -> str:
    """Append one immutable evidence record · returns the new experiment_id."""
    log_p = root / "reports" / "research" / "evidence" / "evidence_log.jsonl"
    log_p.parent.mkdir(parents=True, exist_ok=True)
    experiment_id = f"exp-{uuid.uuid4().hex[:12]}"
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_commit(root),
        "item_id": item_id,
        "experiment_id": experiment_id,
        "market": market,
        "data_snapshot": data_snapshot,
        "pit_status": pit_status,
        "fold_definition": fold_definition,
        "trial_count": trial_count,
        "parameters": parameters,
        "sample_size": sample_size,
        "metrics": metrics,
        "statistical_test": statistical_test,
        "multiple_testing_correction": multiple_testing_correction,
        "decision": decision,
        "artifact_paths": artifact_paths,
    }
    # Append-only · never overwrite
    with open(log_p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return experiment_id


def read_evidence_log(root: Path) -> list[dict]:
    """Read the full log (small enough to keep in memory · consumer paginates)."""
    log_p = root / "reports" / "research" / "evidence" / "evidence_log.jsonl"
    if not log_p.exists(): return []
    out = []
    for line in log_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def latest_for_item(root: Path, item_id: str, market: str | None = None) -> dict | None:
    """Return the most recent record for a given item (+ market if specified)."""
    log = read_evidence_log(root)
    matches = [r for r in log if r.get("item_id") == item_id
                and (market is None or r.get("market") == market)]
    return matches[-1] if matches else None

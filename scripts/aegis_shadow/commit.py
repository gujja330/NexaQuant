"""Recover publication and accepted-checkpoint handoff after interruption."""
from pathlib import Path
import json

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json
from scripts.aegis_shadow.publication import publish


def _checksum(path):
    return digest(path) if path.is_file() else None


def finish(root, private, market, validate):
    journal = contained(private, Path("commit-pending.json"))
    if not journal.is_file() or not (intent := _json(journal)):
        return None
    accepted = contained(private, Path("accepted.json"))
    state = intent["state"]
    if state["market"] != market or state["runner"] != "new":
        raise ValueError("pending commit has incorrect market or runner")
    current = _json(accepted) if accepted.is_file() else {}
    if current.get("commit_workspace") == state["workspace"] and all(current.get(k) == v for k, v in state.items()):
        _atomic(private, journal.name, b"{}")
        return None
    if _checksum(accepted) != intent["parent_sha256"]:
        raise ValueError("pending commit parent changed; checkpoint reconciliation required")
    work = contained(private, Path(state["workspace"]))
    output = contained(private, Path(intent["output"]))
    validate(work, intent["artifact_state"])
    summary = {"market": market, "asof": state["asof"], "market_data_asof": state["market_data_asof"],
               "status": "SHADOW_CERTIFIED", "workbook_sha256": state["workbook_sha256"]}
    publication = publish(root, output, summary)
    _atomic(private, accepted.name, json.dumps(dict(state, workbook=publication["workbook"],
                                                    commit_workspace=state["workspace"])).encode())
    _atomic(private, journal.name, b"{}")
    return publication


def prepare(private, work, output, state, artifact_state):
    if work.relative_to(private).as_posix() != state["workspace"]:
        raise ValueError("commit intent workspace mismatch")
    journal = contained(private, Path("commit-pending.json"))
    if journal.is_file() and _json(journal):
        raise ValueError("previous publication commit must be reconciled first")
    accepted = contained(private, Path("accepted.json"))
    _atomic(private, journal.name, json.dumps({"parent_sha256": _checksum(accepted),
            "state": state, "output": output.relative_to(private).as_posix(), "artifact_state": artifact_state}).encode())

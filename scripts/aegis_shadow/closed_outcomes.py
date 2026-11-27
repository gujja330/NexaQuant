"""Build a closed-outcome research corpus from explicitly reviewed evidence."""
import hashlib
import json
from math import isfinite
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


def _verified_entry(work, reference, market, ticker, episode, admitted, approved_root):
    if reference.get("kind") == "reviewed_input":
        if approved_root is None:
            raise ValueError("reviewed entry evidence root is unavailable")
        path = contained(approved_root, Path("entry_evidence") / reference["path"])
    else:
        path = contained(work, Path(reference["path"]))
    if digest(path) != reference["sha256"]:
        raise ValueError("entry evidence checksum mismatch")
    evidence = _json(path)
    if ((evidence.get("market"), evidence.get("ticker"), evidence.get("episode_id"), evidence.get("decision_session")) !=
            (market, ticker, episode, admitted) or not isinstance(evidence.get("features"), dict) or not evidence["features"]):
        raise ValueError("entry evidence lacks matching episode, session or point-in-time features")
    if not all(isinstance(evidence.get(key), str) and evidence[key].strip() for key in ("model_version", "policy_version", "recommendation_id")):
        raise ValueError("entry decision lineage is incomplete")
    return evidence


def collect(work, market, session, exits, reviewed, *, approved_root=None):
    if reviewed.get("market") != market:
        raise ValueError("closed outcome evidence market mismatch")
    records = {}
    for row in reviewed["outcomes"]:
        key = (row["episode_id"], row["outcome_session"])
        if key in records:
            raise ValueError("duplicate reviewed outcome key")
        records[key] = row
    confirmed, simulated, excluded = [], [], []
    confirmed_keys = set()
    for row in exits:
        pid, date = row.get("position_id"), row.get("exit_date")
        if not pid or not date or date > session:
            continue
        kind = row.get("record_type")
        if kind == "SIMULATED OBSERVATION":
            simulated.append({"episode_id": pid, "session": date, "trigger_session": row.get("trigger_session"),
                              "observation_price": row.get("observation_price"), "classification": "SIMULATED_OBSERVATION"})
            continue
        evidence = records.get((pid, date), {})
        try:
            if kind not in {"REALIZED EXIT", "UNCONFIRMED STOP EXIT", "UNCONFIRMED TARGET EXIT"}:
                raise ValueError(f"ineligible lifecycle classification: {kind}")
            if (pid, date) in confirmed_keys:
                raise ValueError("duplicate lifecycle outcome reference")
            if (evidence.get("execution_status") != "CONFIRMED" or not evidence.get("source")
                    or evidence.get("ticker") != row.get("ticker")):
                raise ValueError("reviewed confirmed execution evidence is unavailable")
            admitted = row["entry_date"]
            if admitted >= date:
                raise ValueError("entry and outcome sessions are unordered")
            entry = _verified_entry(work, evidence["entry_reference"], market, row["ticker"], pid, admitted, approved_root)
            buy, sell = evidence["entry_fill_price"], evidence["exit_fill_price"]
            if any(type(price) not in (int, float) or not isfinite(price) or price <= 0 for price in (buy, sell)):
                raise ValueError("invalid confirmed fill prices")
            output = {"market": market, "episode_id": pid, "ticker": row["ticker"], "entry_session": admitted,
                      "outcome_session": date, "classification": "CONFIRMED_EXECUTION",
                      "entry_fill_price": buy, "exit_fill_price": sell, "gross_return_pct": (sell / buy - 1) * 100,
                      "source": evidence["source"], "entry_reference": evidence["entry_reference"], "decision": entry}
            output["revision_sha256"] = hashlib.sha256(json.dumps(output, sort_keys=True, allow_nan=False).encode()).hexdigest()
            confirmed.append(output)
            confirmed_keys.add((pid, date))
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            excluded.append({"episode_id": pid, "session": date, "reason": str(error)})
    return {"schema": "aegis.shadow.closed_corpus.v1", "market": market, "session": session,
            "confirmed": confirmed, "simulated_observations": simulated, "excluded": excluded}


def emit(context):
    work, market, session = (context[key] for key in ("work", "market", "session"))
    path = contained(context["storage"], Path("inputs") / market / "closed_outcome_evidence.json")
    reviewed = _json(path) if path.is_file() else {"market": market, "outcomes": []}
    lifecycle = _json(contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json")))
    if (lifecycle.get("market"), lifecycle.get("market_data_asof")) != (market, session):
        raise ValueError("closed corpus received mismatched lifecycle evidence")
    report = collect(work, market, session, lifecycle["exits"], reviewed, approved_root=path.parent if path.is_file() else None)
    folder = contained(work, Path("reports/research") / market)
    folder.mkdir(parents=True, exist_ok=True)
    _atomic(folder, "shadow_closed_corpus.json", json.dumps(report, sort_keys=True, indent=2).encode())

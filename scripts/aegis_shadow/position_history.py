"""Retain completed-session pricing and decision evidence by episode."""
import hashlib
import json
from math import isfinite
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


def _positive(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def position_snapshot(lifecycle, risk, exits, market, asof, session, *, prior=None):
    identity = (market, asof)
    if any((doc.get("market"), doc.get("asof")) != identity for doc in (lifecycle, risk, exits)):
        raise ValueError("position history sources disagree with run market or date")
    if lifecycle.get("market_data_asof") != session:
        raise ValueError("position history source has a different completed session")
    updates = {row["opportunity_id"]: row for row in risk["updates"]}
    decisions = {}
    for decision in exits["decisions"]:
        key = decision["opportunity_id"]
        if key in decisions:
            raise ValueError(f"duplicate exit evaluation for {key}")
        decisions[key] = decision
    positions = {}
    prior_positions = (prior or {}).get("positions", {})
    for row in lifecycle["current"]:
        pid = row["position_id"]
        if not pid or pid in positions:
            raise ValueError("missing or duplicate current episode identity")
        decision, update = decisions.get(pid, {}), updates.get(pid, {})
        entry, observed, stop, target = (row.get(field) for field in ("entry_price", "current_price", "stop", "target"))
        price_session = row.get("market_data_asof")
        price_current = price_session == session and _positive(observed)
        pnl = 100 * (observed / entry - 1) if price_current and _positive(entry) else None
        at_stop = 100 * (stop / entry - 1) if _positive(stop) and _positive(entry) else None
        previous = prior_positions.get(pid, {})
        previous_stop = previous.get("effective_stop") if previous.get("entry_date") == row.get("entry_date") else None
        comparable_stop = (_positive(previous_stop) and _positive(stop) and _positive(entry)
                           and previous.get("entry_price") == entry and price_current and previous.get("price_current")
                           and previous.get("stop_source") == row.get("stop_basis")
                           and str(row.get("stop_basis") or "").startswith("dynamic_risk_v2"))
        previous_target = previous.get("target")
        target_reached = price_current and _positive(target) and observed >= target
        previous_achievement = previous.get("first_target_reached_session") if previous_target == target else None
        positions[pid] = {
            "ticker": row.get("ticker"), "engine": row.get("engine"), "entry_date": row.get("entry_date"),
            "entry_price": entry, "observed_price": observed, "price_session": price_session,
            "price_current": price_current, "effective_stop": stop, "stop_source": row.get("stop_basis"),
            "original_stop": row.get("original_stop") or update.get("original_stop"),
            "stop_state": row.get("stop_state"), "stop_type": update.get("stop_type"),
            "stop_reason": update.get("reason"), "return_at_stop_pct": at_stop,
            "proposed_stop": update.get("proposed_stop"), "proposal_type": update.get("proposal_type"),
            "proposal_effective_from": risk.get("proposal_effective_from_session"),
            "stop_effective_for_observation": update.get("effective_for_observation"),
            "previous_effective_stop": previous_stop,
            "stop_change": stop - previous_stop if _positive(stop) and _positive(previous_stop) else None,
            "monotonic_violation": bool(risk.get("monotonic") and comparable_stop and stop < previous_stop),
            "giveback_pp": max(0.0, pnl - at_stop) if pnl is not None and pnl > 0 and at_stop is not None else None,
            "target": target, "target_source": row.get("target_basis"),
            "target_state": ("REACHED" if observed >= target else "NOT_REACHED") if price_current and _positive(target) else "UNAVAILABLE",
            "first_target_reached_session": previous_achievement or (session if target_reached else None),
            "target_t1": decision.get("t1_price"), "target_t2": decision.get("t2_price"),
            "holding_horizon_days": decision.get("horizon_days"), "exit_event": decision.get("event"),
            "exit_action": decision.get("action"), "decision_price_session": decision.get("price_basis_date"),
            "decision_reason": decision.get("reason"),
        }
    events = [row for row in lifecycle["exits"] if row.get("exit_date") in {asof, session}]
    return {"schema": "aegis.shadow.position_history.v1", "market": market, "asof": asof, "session": session,
            "positions": positions, "same_day_exit_evidence": events,
            "exit_evaluations": decisions, "monotonic_policy_enabled": risk.get("monotonic")}


def record(context):
    work, market, asof, session = (context[key] for key in ("work", "market", "asof", "session"))
    scope = {
        "lifecycle": f"reports/context/canonical_lifecycle_{market}.json",
        "risk": f"reports/context/dynamic_risk_{market}.json",
        "exits": f"reports/audit/dynamic_exit_decisions_{market}_{asof}.json",
    }
    prior = None
    pointer = contained(work, Path(".shadow-position-history.json"))
    if pointer.is_file():
        previous_session = context["previous_session"]
        if previous_session != session:
            prior = read(work, market, previous_session)
        else:
            # Compare against the same previous session on a forced repeat.
            # Reading today's prior revision would change the history on every retry.
            accepted = read(work, market, session)
            prior_path = accepted.get("prior_observation")
            if prior_path:
                prior = _read_revision(work, market, prior_path)
    snapshot = position_snapshot(*(_json(contained(work, Path(name))) for name in scope.values()), market, asof, session,
                                 prior=prior)
    if prior is not None:
        snapshot["prior_observation"] = prior["observation_path"]
    payload = json.dumps(snapshot, sort_keys=True, indent=2, allow_nan=False).encode()
    checksum = hashlib.sha256(payload).hexdigest()
    folder = contained(work, Path(f"reports/context/shadow_position_history_{market}") / session)
    folder.mkdir(parents=True, exist_ok=True)
    path = contained(folder, Path(f"{checksum}.json"))
    if path.is_file():
        if digest(path) != checksum:
            raise ValueError("retained position observation checksum mismatch")
    else:
        _atomic(folder, path.name, payload)
    _atomic(work, ".shadow-position-history.json", json.dumps({"path": path.relative_to(work).as_posix(),
                                                               "sha256": checksum}).encode())


def read(work, market, session):
    pointer = _json(contained(work, Path(".shadow-position-history.json")))
    history = _read_revision(work, market, pointer["path"])
    if history["session"] != session or Path(pointer["path"]).stem != pointer["sha256"]:
        raise ValueError("position history identity mismatch")
    return history


def _read_revision(work, market, relative):
    path = contained(work, Path(relative))
    folder = contained(work, Path(f"reports/context/shadow_position_history_{market}"))
    if path.parent.parent != folder or digest(path) != path.stem:
        raise ValueError("position history revision identity mismatch")
    history = _json(path)
    if (history.get("market"), history.get("session")) != (market, path.parent.name):
        raise ValueError("position history market or session mismatch")
    return dict(history, observation_path=relative)

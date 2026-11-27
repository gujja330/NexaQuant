"""Apply evidenced simulated missed-session exits to a private attempt only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from backend.research import opportunity_registry
from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json
from scripts.aegis_shadow.replay import replay
from scripts.aegis_shadow.risk_intervals import resolve


def _ledger(work, market):
    return contained(work, Path(f"reports/context/shadow_recovery_events_{market}.json"))


def _complete_bars(work, market, position, ticker, sessions):
    """Read missing observations from a reviewed immutable price snapshot."""
    source = position.get("bar_source")
    if not source or all(day in position["bars"] for day in sessions):
        return
    if market == "india":
        ticker = ticker.removesuffix(".NS").removesuffix(".BO")
    folder = "data/raw/india" if market == "india" else "usa/data/raw/us"
    path = contained(work, Path(folder) / f"{ticker}_D1.parquet")
    basis = source.get("price_basis")
    if not basis or not path.is_file():
        return
    file_matches = bool(source.get("sha256")) and digest(path) == source["sha256"]
    if not file_matches and not source.get("closes_sha256"):
        return
    import pandas as pd

    prices = pd.read_parquet(path)
    index = pd.to_datetime(prices.index, errors="raise").strftime("%Y-%m-%d")
    if not index.is_unique:
        raise ValueError("reviewed historical price file has duplicate sessions")
    closes = prices["close" if "close" in prices.columns else "Close"]
    selected = {day: float(close) for day, close in zip(index, closes, strict=True) if day in sessions}
    if not file_matches:
        payload = json.dumps({"market": market, "ticker": ticker, "price_basis": basis, "closes": selected},
                             sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if hashlib.sha256(payload).hexdigest() != source["closes_sha256"]:
            return
    for day, close in selected.items():
        position["bars"].setdefault(day, {"close": close, "price_basis": basis})


def recover(work, market, previous, sessions):
    if work.name != "work" or ".aegis-local" not in work.parts or "unified" not in work.parts:
        raise ValueError("missed-session writes require a private unified work tree")
    fixture = contained(work, Path(".shadow-recovery-input.json"))
    evidence = _json(fixture)
    authority_path = contained(work, Path(".shadow-risk-intervals.json"))
    authority = _json(authority_path) if authority_path.is_file() else None
    if (evidence["market"], evidence["last_committed"], evidence["sessions"],
            evidence["completed_through"]) != (market, previous, sessions, sessions[-1]):
        raise ValueError("historical evidence does not match the missing session range")
    registry = opportunity_registry.load_all(work)
    active = {opp.opportunity_id: opp for group in registry.values()
              for opp in group if opp.market == market and opp.is_active()
              and opp.created_date < sessions[-1]}
    supplied = {row["opportunity_id"]: row for row in evidence["positions"]}
    if len(supplied) != len(evidence["positions"]) or any(
            pid not in active or row["admitted"] != active[pid].created_date for pid, row in supplied.items()):
        raise ValueError("historical evidence contains duplicate or inconsistent episode identities")
    # The carry-forward input is only for positions active at the prior
    # checkpoint. Caller-supplied closures cannot truncate their review.
    evidence["positions"] = []
    for pid, episode in active.items():
        position = dict(supplied.get(pid, {}), opportunity_id=pid, admitted=episode.created_date, closed_on=None)
        position.setdefault("bars", {})
        position.setdefault("levels", {})
        if authority:
            interval_sources = []
            for session in sessions:
                if session <= episode.created_date:
                    continue
                approved = resolve(authority, market, pid, episode.ticker, session)
                if approved is None:
                    continue
                level = {key: approved[key] for key in ("stop", "target", "price_basis", "authorized_on", "policy_version")}
                old = position["levels"].get(session)
                if old and any(old.get(key) != level[key] for key in ("stop", "target", "price_basis")):
                    raise ValueError(f"direct and interval risk evidence disagree for {pid} on {session}")
                position["levels"][session] = dict(level, revision_id=approved["revision_id"], source=approved["source"])
                if approved.get("bar_source"):
                    interval_sources.append(approved["bar_source"])
            if not position.get("bar_source") and interval_sources and all(item == interval_sources[0] for item in interval_sources):
                position["bar_source"] = interval_sources[0]
        _complete_bars(work, market, position, episode.ticker, sessions)
        evidence["positions"].append(position)
    report = replay(evidence)
    receipt = ".shadow-recovery-result.json"
    _atomic(work, receipt, json.dumps(report, indent=2).encode())
    if report["pending"]:
        raise ValueError("historical risk evidence unresolved; private registry remains unchanged")
    ledger = _ledger(work, market)
    retained = _json(ledger) if ledger.exists() else []
    seen = {tuple(row["event_id"]) for row in retained}
    detected = datetime.now(timezone.utc).isoformat()
    by_id = {row["opportunity_id"]: row for row in evidence["positions"]}
    for row in report["events"]:
        opp = opportunity_registry.close(
            work, row["opportunity_id"], row["session"],
            reason=f"{row['rule']} | SHADOW HISTORICAL SIMULATION | close={row['trigger_close']}",
            registry=registry,
        )
        if opp is None or opp.status != "CLOSED" or opp.closed_date != row["session"]:
            raise ValueError("private registry rejected the evidenced historical transition")
        key = tuple(row["event_id"])
        if key not in seen:
            levels = by_id[row["opportunity_id"]]["levels"][row["session"]]
            retained.append(dict(row, detected_utc=detected, policy_version=levels.get("policy_version"),
                                 authority_revision=levels.get("revision_id"), authority_source=levels.get("source")))
            seen.add(key)
    if report["events"]:
        _atomic(ledger.parent, ledger.name, json.dumps(retained, indent=2).encode())


def annotate_lifecycle(context):
    """Keep simulated observations out of the common realized-return population."""
    work, market = context["work"], context["market"]
    ledger = _ledger(work, market)
    events = {(row["opportunity_id"], row["session"]): row for row in _json(ledger)} if ledger.is_file() else {}
    path = contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json"))
    lifecycle = _json(path)
    for row in lifecycle["exits"]:
        trigger = row.get("exit_trigger") or ""
        if trigger.startswith(("EXIT_STOP | SHADOW_UNCONFIRMED | ", "EXIT_TARGET | SHADOW_UNCONFIRMED | ")):
            risk_event = trigger.split(" | ", 1)[0]
            row.update(record_type="UNCONFIRMED STOP EXIT" if risk_event == "EXIT_STOP" else "UNCONFIRMED TARGET EXIT",
                       source="shadow:point-in-time-exit",
                       trigger_session=trigger.rsplit(" | ", 1)[1], exit_price=None, realized_pnl_pct=None,
                       observation_price=row.get("exit_price"), execution_status="UNCONFIRMED")
        if (event := events.get((row.get("position_id"), row.get("exit_date")))) is not None:
            row.update(record_type="SIMULATED OBSERVATION", source="shadow:historical-risk-replay",
                       trigger_session=event["session"], exit_price=None, realized_pnl_pct=None,
                       observation_price=event["trigger_close"], execution_status=event["execution_status"],
                       recovered_during_gap=True, recovery_detected_utc=event["detected_utc"],
                       policy_version=event.get("policy_version"))
    _atomic(path.parent, path.name, json.dumps(lifecycle, indent=2).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market", choices=("india", "usa"))
    parser.add_argument("previous")
    parser.add_argument("sessions", nargs="+")
    args = parser.parse_args()
    recover(Path(__file__).resolve().parents[2], args.market, args.previous, args.sessions)


if __name__ == "__main__":
    main()

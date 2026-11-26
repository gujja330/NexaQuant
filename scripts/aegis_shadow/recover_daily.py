"""Apply evidenced simulated missed-session exits to a private attempt only."""
import argparse
import json
from pathlib import Path

from backend.research import opportunity_registry
from scripts.aegis_local_state import contained
from scripts.aegis_shadow.pipeline import _atomic, _json
from scripts.aegis_shadow.replay import replay


def recover(work, market, previous, sessions):
    if work.name != "work" or ".aegis-local" not in work.parts or "unified" not in work.parts:
        raise ValueError("missed-session writes require a private unified work tree")
    fixture = contained(work, Path(".shadow-recovery-input.json"))
    evidence = _json(fixture)
    if (evidence["market"], evidence["last_committed"], evidence["sessions"],
            evidence["completed_through"]) != (market, previous, sessions, sessions[-1]):
        raise ValueError("historical evidence does not match the missing session range")
    registry = opportunity_registry.load_all(work)
    active = {opp.opportunity_id: opp.created_date for group in registry.values()
              for opp in group if opp.market == market and opp.is_active()
              and opp.created_date < sessions[-1]}
    supplied = {row["opportunity_id"]: row["admitted"] for row in evidence["positions"]}
    if supplied != active:
        raise ValueError("historical evidence does not account for every eligible shadow position")
    # The carry-forward input is only for positions active at the prior
    # checkpoint. Caller-supplied closures cannot truncate their review.
    evidence["positions"] = [dict(row, closed_on=None) for row in evidence["positions"]]
    report = replay(evidence)
    receipt = ".shadow-recovery-result.json"
    _atomic(work, receipt, json.dumps(report, indent=2).encode())
    if report["pending"]:
        raise ValueError("historical risk evidence unresolved; private registry remains unchanged")
    for row in report["events"]:
        opp = opportunity_registry.close(
            work, row["opportunity_id"], row["session"],
            reason=f"{row['rule']} | SHADOW HISTORICAL SIMULATION | close={row['trigger_close']}",
            registry=registry,
        )
        if opp is None or opp.status != "CLOSED" or opp.closed_date != row["session"]:
            raise ValueError("private registry rejected the evidenced historical transition")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market", choices=("india", "usa"))
    parser.add_argument("previous")
    parser.add_argument("sessions", nargs="+")
    args = parser.parse_args()
    recover(Path(__file__).resolve().parents[2], args.market, args.previous, args.sessions)


if __name__ == "__main__":
    main()

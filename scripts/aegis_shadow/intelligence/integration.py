"""Isolated daily research report and owner-operated holdout evaluation."""
import hashlib
import json
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.intelligence.assembly import assemble
from scripts.aegis_shadow.intelligence.lab import evaluate, forecasts, momentum_state, number, validate
from scripts.aegis_shadow.intelligence.management import entry, position
from scripts.aegis_shadow.intelligence.opportunities import rank
from scripts.aegis_shadow.intelligence.strategy_replay import evaluate_management
from scripts.aegis_shadow.pipeline import _atomic, _json
from scripts.aegis_shadow.position_history import read


def _panel(path, market):
    payload = path.read_bytes()
    document = json.loads(payload)
    rows = validate(document, market)
    minimum = document.get("minimum_observations")
    if type(minimum) is not int or minimum < 2:
        raise ValueError("research panel requires a minimum observation count of at least two")
    return document, rows, minimum, hashlib.sha256(payload).hexdigest()


def panel(storage, market):
    return _panel(contained(storage, Path("inputs") / market / "research_panel.json"), market)


def accepted_panel(storage, market):
    private = contained(storage, Path("daily") / market)
    checkpoint = _json(contained(private, Path("accepted.json")))
    if checkpoint.get("market") != market or checkpoint.get("runner") != "new":
        raise ValueError("accepted research workspace identity mismatch")
    workspace = contained(private, Path(checkpoint["workspace"]))
    relative = Path(f"reports/research/intelligence/{market}/prepared_panel.json")
    result = _panel(contained(workspace, relative), market)
    if result[-1] != checkpoint.get("certification_state", {}).get(relative.as_posix()):
        raise ValueError("prepared research panel does not match accepted checkpoint")
    return result


def review(positions):
    output = []
    for episode, row in sorted(positions.items()):
        entry, price, stop = (row.get(key) for key in ("entry_price", "observed_price", "effective_stop"))
        valid = row.get("price_current") and all(number(value) and value > 0 for value in (entry, price))
        risk_valid = valid and row.get("stop_effective_for_observation") is True and number(stop) and stop > 0
        output.append({"episode_id": episode, "ticker": row.get("ticker"), "classification": "OBSERVATION_ONLY",
                       "observed_return": price / entry - 1 if valid else None,
                       "indicative_return_at_effective_stop": stop / entry - 1 if risk_valid else None,
                       "profit_giveback_pp": max(0, (price - stop) / entry * 100) if risk_valid and price > entry else None,
                       "target_state": row.get("target_state"), "effective_stop_evidence": bool(risk_valid)})
    return output


def management_reviews(journal, rows, session, minimum, previous_exits, open_research):
    entries = []
    holdings = []
    current = {(row["security_id"], row["horizon"]): row for row in rows if row["session"] == session
               and row.get("available_on", session) <= session}
    eligible = forecasts(rows, session, minimum)
    opportunities = {(item["security_id"], item["horizon"]): item for item in rank(rows, session, eligible)}
    held = {row.get("ticker") for row in journal["positions"].values()}
    for estimate in eligible:
        key = estimate["security_id"], estimate["horizon"]
        row = current[key]
        if row.get("ticker") not in held:
            candidate = entry(row, estimate["net_return_distribution"], opportunities[key],
                              can_reenter=row.get("ticker") in previous_exits)
            entries.append(dict(candidate, classification="RESEARCH_ONLY", score=opportunities[key].get("score")))
    history = {(item["security_id"], item["horizon"]): item["net_return_distribution"]
               for item in forecasts(rows, session, minimum, include_ineligible=True)}
    prior_day = max((row["session"] for row in rows if row["session"] < session), default=None)
    prior_rows = {(row["security_id"], row["horizon"]): row for row in rows if row["session"] == prior_day
                  and row.get("available_on", prior_day) <= prior_day}
    prior_forecasts = {(item["security_id"], item["horizon"]): item["net_return_distribution"]
                       for item in forecasts(rows, prior_day, minimum, include_ineligible=True)} if prior_day else {}
    by_ticker = {}
    for key, row in sorted(current.items(), key=lambda item: (abs(item[0][1] - 20), item[0])):
        by_ticker.setdefault(row.get("ticker"), (row, history.get(key)))
    for episode, observed in sorted(journal["positions"].items()):
        row, forecast = by_ticker.get(observed.get("ticker"), ({}, None))
        earlier = open_research.get(episode, {})
        peak = None
        if (earlier.get("entry_reference") == observed.get("entry_price") and not earlier.get("entry_reference_conflict")
                and number(earlier.get("max_observed_return_pct")) and number(observed.get("entry_price"))):
            peak = observed["entry_price"] * (1 + earlier["max_observed_return_pct"] / 100)
        key = row.get("security_id"), row.get("horizon")
        alternatives = [item["expected_net_return"] - item["downside"] for item in opportunities.values()
                        if item["status"] == "RESEARCH_CANDIDATE" and item["horizon"] == key[1]
                        and item["security_id"] != key[0] and current[(item["security_id"], item["horizon"])].get("ticker") not in held]
        holdings.append(dict(position(row, observed, forecast, peak, previous=prior_rows.get(key),
                                      previous_forecast=prior_forecasts.get(key), alternative=max(alternatives, default=None)),
                             episode_id=episode, ticker=observed.get("ticker"),
                             momentum_state=momentum_state(row) if row else None,
                             classification="RESEARCH_ONLY", proposal_timing="AFTER_OBSERVATION_CLOSE"))
    return entries, holdings


def emit(context):
    work, storage, market, session = (context[key] for key in ("work", "storage", "market", "session"))
    journal = read(work, market, session)
    research = {"market": market, "session": session, "schema": "aegis.shadow.strategy_research.v1",
                "classification": "RESEARCH_ONLY", "forecast_status": "PANEL_UNAVAILABLE", "forecasts": [],
                "position_reviews": review(journal["positions"])}
    try:
        document, rows, minimum, checksum = panel(storage, market)
    except FileNotFoundError:
        document = assemble(context, journal=journal)
        if document is not None:
            prepared = contained(work, Path(f"reports/research/intelligence/{market}/prepared_panel.json"))
            document, rows, minimum, checksum = _panel(prepared, market)
    if document is not None:
        predictions = forecasts(rows, session, minimum)
        research.update(forecast_status="RESEARCH_ESTIMATES" if any(item["net_return_distribution"] for item in predictions)
                        else "INSUFFICIENT_EVIDENCE", forecasts=predictions, panel_sha256=checksum,
                        opportunities=rank(rows, session, predictions),
                        benchmark_id=document["benchmark_id"], minimum_observations=minimum)
    lifecycle_path = contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json"))
    lifecycle = _json(lifecycle_path) if lifecycle_path.is_file() else {}
    eligible_exits = {row.get("ticker") for row in lifecycle.get("exits", ()) if row.get("exit_date")
                      and row["exit_date"] < session and row.get("record_type") == "REALIZED EXIT"}
    history_path = contained(work, Path(f"reports/research/{market}/shadow_open_episode_research.json"))
    receipt_path = contained(work, Path(".shadow-open-cohort-cache.json"))
    history = {}
    if receipt_path.is_file() and history_path.is_file():
        receipt = _json(receipt_path)
        chain = receipt.get("inputs", {}).get("chain", [])
        if chain and chain[0] == journal.get("observation_path") and receipt.get("output_sha256") == digest(history_path):
            history = _json(history_path)
    peaks = history.get("current_cohort", {}) if (history.get("market"), history.get("session")) == (market, session) else {}
    entries, holdings = management_reviews(journal, rows if document is not None else [], session,
                                           minimum if document is not None else 30, eligible_exits, peaks)
    research.update(entry_candidates=entries, management_reviews=holdings)
    folder = contained(work, Path("reports/research/intelligence") / market)
    folder.mkdir(parents=True, exist_ok=True)
    history = contained(folder, Path("management_history") / session)
    history.mkdir(parents=True, exist_ok=True)
    snapshot = json.dumps({"classification": "RESEARCH_ONLY", "market": market, "session": session,
                           "journal_observation": journal.get("observation_path"), "entry_candidates": entries,
                           "management_reviews": holdings}, sort_keys=True, indent=2, allow_nan=False).encode()
    revision = hashlib.sha256(snapshot).hexdigest() + ".json"
    path = contained(history, Path(revision))
    if path.is_file() and path.read_bytes() != snapshot:
        raise ValueError("retained management observation checksum mismatch")
    if not path.exists():
        _atomic(history, revision, snapshot)
    research["management_observation"] = path.relative_to(work).as_posix()
    _atomic(folder, "strategy_research.json", json.dumps(research, sort_keys=True, indent=2, allow_nan=False).encode())


def run_holdout(root, markets):
    storage = contained(root, Path(".aegis-local/unified"))
    failed = False
    for market in markets:
        try:
            try:
                document, rows, minimum, checksum = panel(storage, market)
            except FileNotFoundError:
                document, rows, minimum, checksum = accepted_panel(storage, market)
            holdout_path = contained(storage, Path("inputs") / market / "research_holdout.json")
            holdout = _json(holdout_path) if holdout_path.is_file() else document["holdout"]
            settings = (rows, holdout["start"], holdout["end"], holdout["known_through"], minimum)
            report = evaluate(*settings)
            report["frozen_holdout"] = evaluate(*settings, frozen=True)
            report["management_walk_forward"] = evaluate_management(*settings)
            report["management_frozen_holdout"] = evaluate_management(*settings, frozen=True)
            if holdout.get("evaluate_models") is True:
                from scripts.aegis_shadow.intelligence.models import evaluate_models

                report["model_challengers"] = evaluate_models(*settings)
                report["frozen_model_challengers"] = evaluate_models(*settings, frozen=True)
            report.update(market=market, holdout=holdout, panel_sha256=checksum, benchmark_id=document["benchmark_id"],
                          minimum_observations=minimum, method="conditional_empirical_net_return_v1")
            payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode()
            folder = contained(storage, Path("research/intelligence") / market / "holdouts")
            folder.mkdir(parents=True, exist_ok=True)
            name = hashlib.sha256(payload).hexdigest() + ".json"
            destination = contained(folder, Path(name))
            if destination.is_file() and destination.read_bytes() != payload:
                raise ValueError("retained holdout result checksum mismatch")
            if not destination.exists():
                _atomic(folder, name, payload)
            print(f"{market} research holdout {destination}")
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            print(f"{market} research holdout unavailable | {error}")
            failed = True
    return int(failed)

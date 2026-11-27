"""Derive a research-only longitudinal cohort from accepted price observations."""
import json
from math import isfinite
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json
from scripts.aegis_shadow.position_history import _read_revision, read


def summarize(revisions):
    cohort = {}
    for revision in revisions:
        session = revision["session"]
        for episode, row in revision["positions"].items():
            if not row.get("price_current"):
                continue
            entry, close = row.get("entry_price"), row.get("observed_price")
            if any(type(value) not in (float, int) or not isfinite(value) or value <= 0 for value in (entry, close)):
                continue
            pnl = 100 * (close / entry - 1)
            item = cohort.setdefault(episode, {"entry_date": row.get("entry_date"), "entry_reference": entry,
                                               "observations": 0, "entry_reference_conflict": False,
                                               "max_observed_return_pct": pnl, "min_observed_return_pct": pnl})
            if (item["entry_date"], item["entry_reference"]) != (row.get("entry_date"), entry):
                item["entry_reference_conflict"] = True
                continue
            item["observations"] += 1
            item["last_observed_session"] = session
            item["max_observed_return_pct"] = max(item["max_observed_return_pct"], pnl)
            item["min_observed_return_pct"] = min(item["min_observed_return_pct"], pnl)
            if pnl > 0:
                item.setdefault("first_profitable_observation", session)
            if row.get("target_state") == "REACHED":
                item.setdefault("first_target_observation", session)
    return cohort


def emit(context):
    work, market, session = (context[key] for key in ("work", "market", "session"))
    latest = read(work, market, session)
    revisions = [latest]
    while previous := revisions[-1].get("prior_observation"):
        document = _read_revision(work, market, previous)
        if document["session"] >= revisions[-1]["session"]:
            raise ValueError("position research lineage is not chronological")
        revisions.append(document)
    folder = contained(work, Path("reports/research") / market)
    folder.mkdir(parents=True, exist_ok=True)
    name = "shadow_open_episode_research.json"
    output = contained(folder, Path(name))
    receipt = contained(work, Path(".shadow-open-cohort-cache.json"))
    inputs = {"market": market, "session": session, "chain": [row["observation_path"] for row in revisions],
              "implementation_sha256": digest(contained(work, Path("scripts/aegis_shadow/learning_observations.py")))}
    if not context.get("force") and receipt.is_file() and output.is_file():
        try:
            if _json(receipt) == {"inputs": inputs, "output_sha256": digest(output)}:
                if context.get("mode") == "FULL":
                    context["mode"] = "INCREMENTAL"
                return "REUSED"
        except (OSError, TypeError, ValueError):
            pass
    cohort = summarize(reversed(revisions))
    tracked = {episode: cohort[episode] for episode in latest["positions"] if episode in cohort}
    _atomic(folder, name, json.dumps({
        "schema": "aegis.shadow.open_episode_research.v1", "market": market, "session": session,
        "classification": "OPEN_OBSERVATIONS_ONLY", "observed_sessions": len(revisions),
        "current_cohort": tracked, "historical_episode_observations": cohort,
    }, indent=2, sort_keys=True).encode())
    _atomic(work, receipt.name, json.dumps({"inputs": inputs, "output_sha256": digest(output)}).encode())

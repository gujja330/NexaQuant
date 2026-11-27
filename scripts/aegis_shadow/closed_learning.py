"""Consume the verified closed cohort for independent research metrics."""
import json
from math import isfinite
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


def evaluate(corpus, market, session):
    if (corpus.get("schema"), corpus.get("market"), corpus.get("session")) != (
            "aegis.shadow.closed_corpus.v1", market, session):
        raise ValueError("closed learning corpus identity mismatch")
    by_model, seen = {}, set()
    for row in corpus["confirmed"]:
        key = (row["episode_id"], row["outcome_session"])
        if (row.get("market") != market or row.get("classification") != "CONFIRMED_EXECUTION"
                or key in seen or not row["entry_session"] < row["outcome_session"] <= session):
            raise ValueError("closed learning corpus contains a wrong-market, duplicate or ineligible outcome")
        seen.add(key)
        result = row["gross_return_pct"]
        if not isfinite(result):
            raise ValueError("closed return is not finite")
        decision = row["decision"]
        pair = (decision["model_version"], decision["policy_version"])
        metrics = by_model.setdefault(pair, {"observations": 0, "wins": 0, "returns": 0.0,
                                             "calibration_samples": 0, "squared_error": 0.0})
        metrics["observations"] += 1
        metrics["wins"] += int(result > 0)
        metrics["returns"] += result
        score = decision.get("probability_positive")
        if type(score) in (int, float) and 0 <= score <= 1 and decision.get("probability_outcome") == "POSITIVE_GROSS_RETURN_AT_EXIT":
            metrics["calibration_samples"] += 1
            metrics["squared_error"] += (score - int(result > 0)) ** 2
    models = []
    for (model, policy), metrics in sorted(by_model.items()):
        n, samples = metrics["observations"], metrics["calibration_samples"]
        models.append({"model_version": model, "policy_version": policy, "observations": n,
                       "gross_win_rate": metrics["wins"] / n, "mean_gross_return_pct": metrics["returns"] / n,
                       "calibration_samples": samples, "brier_score": metrics["squared_error"] / samples if samples else None})
    return {"market": market, "session": session, "confirmed_consumed": len(seen),
            "simulated_excluded": len(corpus["simulated_observations"]), "other_excluded": len(corpus["excluded"]),
            "groups": models, "basis": "Reviewed gross return at exit, grouped by entry model and policy"}


def emit(context):
    work, market, session = (context[key] for key in ("work", "market", "session"))
    folder = contained(work, Path("reports/research") / market)
    corpus = contained(folder, Path("shadow_closed_corpus.json"))
    expected = {"market": market, "session": session, "corpus_sha256": digest(corpus),
                "implementation_sha256": digest(contained(work, Path("scripts/aegis_shadow/closed_learning.py")))}
    output = contained(folder, Path("shadow_closed_learning.json"))
    receipt = contained(work, Path(".shadow-closed-learning-cache.json"))
    if not context.get("force") and output.is_file() and receipt.is_file():
        try:
            if _json(receipt) == {"inputs": expected, "output_sha256": digest(output)}:
                if context.get("mode") == "FULL":
                    context["mode"] = "INCREMENTAL"
                return "REUSED"
        except (OSError, TypeError, ValueError):
            pass
    report = evaluate(_json(corpus), market, session)
    report["corpus_sha256"] = expected["corpus_sha256"]
    _atomic(folder, output.name, json.dumps(report, sort_keys=True, indent=2).encode())
    _atomic(work, receipt.name, json.dumps({"inputs": expected, "output_sha256": digest(output)}).encode())

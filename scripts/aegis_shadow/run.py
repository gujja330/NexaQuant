"""Frozen-evidence shadow CLI. Makes no subprocess, network, or write calls."""
from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path

from scripts.aegis_shadow.replay import replay
from scripts.aegis_shadow.research import profit_capture


_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACTS = (
    ("universe", "{reports}/universe.json"),
    ("features", "features/{market}/{asof}.parquet"),
    ("model_registry", "model_registry.jsonl"),
    ("recommendations", "{reports}/recommendations.json"),
    ("lifecycle", "reports/context/canonical_lifecycle_{market}.json"),
    ("registry", "reports/research/opportunity_registry.jsonl"),
    ("risk", "reports/context/dynamic_risk_{market}.json"),
    ("portfolio", "{reports}/portfolio_v3.json"),
    ("outcomes", "reports/research/{market}/outcome_dataset.parquet"),
    ("backend", "{reports}/backend_validation_summary.json"),
    ("workbook", "reports/telegram/aegis_{market}_{asof}.xlsx"),
)


def _frozen_path(repo, path):
    storage = (repo / ".aegis-local").resolve()
    if storage.parent != repo or storage.name != ".aegis-local":
        raise ValueError("invalid local evidence root")
    result = (repo / path).resolve(strict=True)
    if not result.is_relative_to(storage) or result == storage:
        raise ValueError("frozen evidence must be beneath .aegis-local")
    return result


def _digest(root, path):
    artifact = (root / path).resolve()
    if not artifact.is_relative_to(root):
        raise ValueError(f"artifact escapes frozen input: {path}")
    if not artifact.is_file():
        return None
    with artifact.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def compare(left, right, market, asof):
    values = {"reports": "usa/reports" if market == "usa" else "reports",
              "market": market, "asof": asof}
    rows = []
    for name, template in _ARTIFACTS:
        path = template.format(**values)
        baseline, candidate = _digest(left, path), _digest(right, path)
        status = "MISSING" if not baseline or not candidate else (
            "MATCH" if baseline == candidate else "DIFFERENT")
        rows.append({"artifact": name, "path": path, "status": status,
                     "baseline_sha256": baseline, "candidate_sha256": candidate})
    return rows


def governance(registry):
    from dataclasses import asdict
    from backend.feature_store.feature_registry import list_features

    models = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    return {"features": [asdict(feature) for feature in list_features()],
            "model_registry_rows": models}


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    replay_parser = commands.add_parser("replay")
    replay_parser.add_argument("fixture", type=Path)
    capture_parser = commands.add_parser("profit-capture")
    capture_parser.add_argument("fixture", type=Path)
    governance_parser = commands.add_parser("governance")
    governance_parser.add_argument("registry", type=Path)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--market", choices=("india", "usa"), required=True)
    compare_parser.add_argument("--asof", required=True)
    compare_parser.add_argument("baseline", type=Path)
    compare_parser.add_argument("candidate", type=Path)
    args = parser.parse_args(argv)
    if args.command == "replay":
        fixture = _frozen_path(_ROOT, args.fixture)
        report = replay(json.loads(fixture.read_text(encoding="utf-8")))
        success = not report["pending"]
    elif args.command == "profit-capture":
        fixture = _frozen_path(_ROOT, args.fixture)
        report = profit_capture(json.loads(fixture.read_text(encoding="utf-8")))
        success = bool(report["episodes"]) and not report["excluded_ids"]
    elif args.command == "governance":
        report = governance(_frozen_path(_ROOT, args.registry))
        success = True
    else:
        from datetime import date

        asof = date.fromisoformat(args.asof).isoformat()
        left = _frozen_path(_ROOT, args.baseline)
        right = _frozen_path(_ROOT, args.candidate)
        if not left.is_dir() or not right.is_dir() or left == right:
            parser.error("provide two distinct frozen work directories")
        report = compare(left, right, args.market, asof)
        success = all(row["status"] == "MATCH" for row in report)
    print(json.dumps(report, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

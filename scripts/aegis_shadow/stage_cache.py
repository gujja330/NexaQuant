"""Checksummed reuse for the benchmark-regime research artifact."""
import ast
from importlib.metadata import version
import json
from pathlib import Path
import sys

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


def regime_cache(context, binding):
    work, market = context["work"], context["market"]
    sources = ("backend/research/mr_market_regime.py", "backend/research/mr_runner.py",
               "scripts/aegis_shadow/stage_cache.py", "scripts/aegis_shadow/worker.py")
    tree = ast.parse(contained(work, Path(sources[0])).read_bytes())
    paths = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "INDEX_PATH" for target in node.targets))
    files = [contained(work, Path(name)) for name in (*sources, *ast.literal_eval(paths)[market])]
    identity = {"schema": "aegis.stage.regime.v1", "market": market, "session": context["session"],
                "command": list(binding.command), "python": sys.version,
                "packages": {name: version(name) for name in ("pandas", "pyarrow")},
                "files": {path.relative_to(work).as_posix(): digest(path) if path.is_file() else None
                          for path in files}}
    receipt = contained(work, Path(".shadow-regime-cache.json"))
    output = contained(work, Path(binding.outputs[0]))
    return receipt, output, identity


def valid_regime(output, market, session):
    report = _json(output)
    regimes = report.get("regimes")
    return (report.get("market") == market.upper() and report.get("status") == "OK"
            and isinstance(regimes, dict) and bool(regimes) and max(regimes) == session)


def reuse_regime(cache, market, session):
    receipt, output, identity = cache
    try:
        return (_json(receipt) == {"identity": identity, "output_sha256": digest(output)}
                and valid_regime(output, market, session))
    except (OSError, TypeError, ValueError):
        return False


def seal_regime(cache, market, session):
    receipt, output, identity = cache
    if not valid_regime(output, market, session):
        raise ValueError("market regime lacks the completed-session benchmark observation")
    _atomic(receipt.parent, receipt.name, json.dumps({"identity": identity, "output_sha256": digest(output)}).encode())

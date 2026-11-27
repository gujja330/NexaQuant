"""Version the local dependencies used by the private daily runner."""
import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic
from backend.shared.atomic_io import replace_with_retry


_CODE_ROOTS = ("backend", "scripts", "india", "core", "data", "execution",
               "markets", "research", "strategy", "nexaquant", "tools", "validation")
_EXCLUDED = {"__pycache__", "archive", "docs", "reports", "dashboard", "raw", "cache", "tests"}
_CONFIG_TYPES = {".yaml", ".yml", ".json", ".toml", ".ini", ".csv", ".txt"}
_MODEL_TYPES = {".pkl", ".pickle", ".joblib", ".onnx", ".ubj", ".cbm"}


def dependencies(root, market):
    source = {}
    code_roots = (*_CODE_ROOTS, "usa") if market == "usa" else _CODE_ROOTS
    for name in code_roots:
        folder = root / name
        for path in folder.rglob("*.py"):
            rel = path.relative_to(root)
            if not _EXCLUDED.intersection(rel.parts[:-1]) and rel.as_posix() != "scripts/aegis_run_all.py":
                source[rel.as_posix()] = digest(contained(root, rel))
    config_roots = ("config", "configs", "usa/configs") if market == "usa" else ("config", "configs")
    for name in config_roots:
        for path in (root / name).rglob("*"):
            rel = path.relative_to(root)
            if path.is_file() and path.suffix in _CONFIG_TYPES:
                source[rel.as_posix()] = digest(contained(root, rel))
    for path in (*root.glob("requirements*.txt"), *root.glob("*.py")):
        source[path.name] = digest(contained(root, Path(path.name)))
    for pattern in ("model_registry.jsonl", "models/**/*", f"{market}/models/**/*",
                    f"{market}/reports/**/*", "reports/models/**/*"):
        for path in root.glob(pattern):
            if path.is_file() and (path.suffix in _MODEL_TYPES or path.name == "model_registry.jsonl"):
                rel = path.relative_to(root)
                source[rel.as_posix()] = digest(contained(root, rel))

    inputs = {}
    patterns = (f"data/raw/{market}/**/*", f"{market}/data/raw/**/*",
                f"data/{market}/raw/**/*", f"features/{market}/**/*",
                "usa/reports/security_master/sp500.json" if market == "usa" else
                "reports/context/india_price_availability.json",
                f".aegis-local/unified/inputs/{market}/shadow_recovery.json",
                f".aegis-local/unified/inputs/{market}/exchange_calendar.json",
                f".aegis-local/unified/inputs/{market}/simulator_opening.json",
                f".aegis-local/unified/inputs/{market}/refresh_policy.json",
                f".aegis-local/unified/inputs/{market}/operations.json",
                f".aegis-local/unified/inputs/{market}/closed_outcome_evidence.json",
                f".aegis-local/unified/inputs/{market}/entry_evidence/**/*.json",
                f".aegis-local/unified/inputs/{market}/exit_authority.json",
                f".aegis-local/unified/inputs/{market}/risk_intervals.json",
                f".aegis-local/unified/inputs/{market}/research_panel.json",
                f".aegis-local/unified/inputs/{market}/provider_policy.json")
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            stat = contained(root, rel).stat()
            # Large local data files use filesystem change identity. Small
            # policy files and reviewed replay evidence use content identity.
            inputs[rel.as_posix()] = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
            if path.suffix == ".json":
                inputs[rel.as_posix()].append(digest(path))
    return {"source_config": source, "market_inputs": inputs}


def sync_dependencies(root, work, market, live, previous, *, session=None):
    copied = dependencies(work, market)["source_config"]
    source = live["source_config"]
    old_source = previous.get("source_config", {})
    for name in copied.keys() - source.keys():
        if name in old_source or not old_source:
            contained(work, Path(name)).unlink()
    for name, checksum in source.items():
        if copied.get(name) != checksum:
            _copy(root, work, name)
            if digest(contained(work, Path(name))) != checksum:
                raise ValueError(f"source changed while copying: {name}")
    # Merge market data updates without replacing the accepted private
    # registry, sealed features, or previous lifecycle checkpoint.
    old_inputs = previous.get("market_inputs", {})
    receipts = {}
    for name, identity in live["market_inputs"].items():
        if old_inputs.get(name) == identity or not name.startswith((
                f"data/raw/{market}/", f"{market}/data/raw/", f"data/{market}/raw/")):
            continue
        if not name.endswith("_D1.parquet"):
            continue
        rel = Path(name)
        source_path, target = contained(root, rel), contained(work, rel)
        try:
            receipts[name] = {"appended_sessions": _append_price_history(source_path, target, session)}
        except Exception as error:
            receipts[name] = {"rejected": str(error)}
            print(f"{market} retained private price history for {name} | {error}", flush=True)
    if receipts:
        _atomic(work, ".shadow-price-import.json", json.dumps(receipts, indent=2).encode())


def _append_price_history(source, target, session):
    import pandas as pd

    incoming = pd.read_parquet(source)
    if not isinstance(incoming.index, pd.DatetimeIndex) or incoming.index.tz is not None:
        raise ValueError("incoming price index must contain timezone-naive session dates")
    if not incoming.index.is_unique or not incoming.index.is_monotonic_increasing:
        raise ValueError("incoming price history must have ordered, unique sessions")
    if session is not None:
        incoming = incoming.loc[incoming.index <= pd.Timestamp(session)]
    if incoming.empty:
        return 0
    if not target.exists():
        result, added = incoming, incoming
    else:
        saved = pd.read_parquet(target)
        if (not isinstance(saved.index, pd.DatetimeIndex) or saved.index.tz is not None
                or not saved.index.is_unique or not saved.index.is_monotonic_increasing):
            raise ValueError("accepted price history has an invalid session index")
        added = incoming.loc[~incoming.index.isin(saved.index)]
        if added.empty:
            return 0
        overlap = saved.index.intersection(incoming.index)
        if len(overlap) < 5 or not saved.columns.isin(incoming.columns).all():
            raise ValueError("insufficient common history or columns to verify price basis")
        ratio = incoming.loc[overlap, "close"] / saved.loc[overlap, "close"]
        if not ((ratio - 1).abs() <= 0.00005).all():
            raise ValueError("saved and incoming price bases disagree")
        result = pd.concat((saved, added.loc[:, saved.columns].rename_axis(saved.index.name))).sort_index()
    from math import isfinite

    if not all(isfinite(value) and value > 0 for value in added["close"]):
        raise ValueError("incoming price history has an invalid close")
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        result.to_parquet(temporary)
        replace_with_retry(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return len(added)


def _copy(root, work, name):
    rel = Path(name)
    target = contained(work, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(contained(root, rel), target)

"""Retain stage evidence independently of the accepted investment checkpoint."""
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from backend.shared.atomic_io import replace_with_retry
from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic


def _object(root, source):
    checksum = digest(source)
    folder = contained(root, Path("objects") / checksum[:2])
    folder.mkdir(parents=True, exist_ok=True)
    target = contained(folder, Path(checksum))
    if target.is_file():
        if digest(target) != checksum:
            raise ValueError("historical evidence object checksum mismatch")
        return checksum
    temporary = None
    try:
        with source.open("rb") as original, NamedTemporaryFile(dir=folder, delete=False) as stream:
            temporary = Path(stream.name)
            shutil.copyfileobj(original, stream)
        if digest(temporary) != checksum:
            raise ValueError("source evidence changed while being archived")
        replace_with_retry(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return checksum


def retain(storage, work, summary, artifacts):
    """Archive a run's observed outputs, including independently valid degraded evidence."""
    market, session = summary["market"], summary["market_data_asof"]
    root = contained(storage, Path("history") / market)
    root.mkdir(parents=True, exist_ok=True)
    files, rejected = {}, {}
    for stage, paths in sorted(artifacts.items()):
        for source in sorted(paths):
            relative = source.relative_to(work).as_posix()
            try:
                safe = contained(work, Path(relative))
                checksum = _object(root, safe)
                entry = files.setdefault(relative, {"sha256": checksum, "bytes": safe.stat().st_size, "stages": []})
                if entry["sha256"] != checksum:
                    raise ValueError("artifact changed between stage references")
                entry["stages"].append(stage)
            except (OSError, RuntimeError, ValueError) as error:
                rejected[relative] = str(error)
    manifest = {"schema": "aegis.shadow.evidence.v1", "runner": "new", "market": market,
                "session": session, "asof": summary["asof"], "validation_status": summary["status"],
                "stage_status": {name: item["status"] for name, item in summary["stages"].items()},
                "files": files, "rejected": rejected}
    payload = json.dumps(manifest, sort_keys=True, indent=2).encode()
    checksum = hashlib.sha256(payload).hexdigest()
    folder = contained(root, Path("sessions") / session)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{checksum}.json"
    target = contained(folder, Path(name))
    if not target.exists():
        _atomic(folder, name, payload)
    elif digest(target) != checksum:
        raise ValueError("historical evidence manifest checksum mismatch")
    return {"manifest": target.relative_to(storage).as_posix(), "artifacts": len(files), "rejected": rejected}

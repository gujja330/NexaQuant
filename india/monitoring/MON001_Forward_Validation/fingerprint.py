"""
MON001 production baseline fingerprint.

Deterministically hashes the frozen production configuration + module source. Any change to
the referenced files' bytes or the referenced constants changes the fingerprint. MON001 uses
this to detect CONFIG_DRIFT — silent strategy drift without an authorized promotion.

Reads-only. Never modifies any production file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def compute_fingerprint(repo_root: Path, baseline_files: list[str],
                        baseline_constants: dict) -> dict:
    """Return a dict describing the current production fingerprint.

    - `files`: {path: sha256} for every baseline file (relative to repo_root).
    - `constants`: canonical JSON of the sealed baseline constants dict.
    - `hash`: SHA-256 of the JSON-serialization of {files, constants}.

    Callers compare `hash` against the sealed hash recorded at MON001 seal time. Any
    difference is CONFIG_DRIFT.
    """
    files_hashes: dict[str, str] = {}
    missing: list[str] = []
    for rel in baseline_files:
        p = (repo_root / rel).resolve()
        if not p.exists():
            missing.append(rel)
            continue
        files_hashes[rel] = _sha256_file(p)

    if missing:
        raise FileNotFoundError(
            f"baseline files missing from repo root {repo_root}: {missing}. "
            f"Cannot compute production fingerprint.")

    canonical_constants = json.dumps(baseline_constants, sort_keys=True,
                                     ensure_ascii=False, default=str)
    payload = json.dumps(
        {"files": files_hashes, "constants": canonical_constants},
        sort_keys=True, ensure_ascii=False,
    )
    return {
        "files": files_hashes,
        "constants": canonical_constants,
        "hash": _sha256_bytes(payload.encode("utf-8")),
    }


def is_drift(current_fp: dict, sealed_fp_hash: str) -> bool:
    """Return True if the current fingerprint hash differs from the sealed hash."""
    return current_fp["hash"] != sealed_fp_hash


def format_drift_report(current_fp: dict, sealed_fp: dict) -> str:
    """Human-readable diff for the reports/alerts pipeline. Never modifies inputs."""
    lines = ["CONFIG_DRIFT detected — production baseline has changed since MON001 seal."]
    if current_fp["hash"] == sealed_fp["hash"]:
        return "no drift"
    lines.append(f"Sealed hash:  {sealed_fp['hash']}")
    lines.append(f"Current hash: {current_fp['hash']}")
    sealed_files = sealed_fp.get("files", {})
    for path, curr_hash in current_fp["files"].items():
        seal_hash = sealed_files.get(path)
        if seal_hash != curr_hash:
            lines.append(f"  changed: {path}")
            lines.append(f"    sealed:  {seal_hash}")
            lines.append(f"    current: {curr_hash}")
    if sealed_fp.get("constants") != current_fp.get("constants"):
        lines.append("  changed: baseline_constants")
        lines.append(f"    sealed:  {sealed_fp.get('constants')}")
        lines.append(f"    current: {current_fp.get('constants')}")
    return "\n".join(lines)

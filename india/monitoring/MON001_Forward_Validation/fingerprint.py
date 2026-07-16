"""
MON001 production baseline fingerprint.

Deterministically hashes the frozen production configuration + module source. Any
CONTENT change to the referenced files' bytes or the referenced constants changes
the fingerprint. MON001 uses this to detect CONFIG_DRIFT — silent strategy drift
without an authorized promotion.

Reads-only. Never modifies any production file.

Algorithm versioning
--------------------
`ALGORITHM_VERSION` is the currently-implemented fingerprint algorithm. Auditors
comparing hashes across time can verify both parties are using the same version;
a change in `ALGORITHM_VERSION` REQUIRES a documented re-seal ceremony per
`docs/CHANGE_CONTROL_CHECKLIST.md` §3.

- v1 (deprecated, 2026-07-13 → 2026-07-15): raw file bytes → SHA-256.
       Platform-dependent (Windows CRLF vs Linux/CI LF produced different hashes
       for the same source content). Only used for historical MON001 seal at
       hash `064d8b04eb85b8194e02b07a07ead207770d598be72c46e4ec7698add912d52f`.

- v2 (current, 2026-07-15 →): LF-normalized UTF-8 bytes → SHA-256.
       Line endings normalized (`\\r\\n` → `\\n`) before hashing so the same
       source content produces the same hash on Windows / Linux / macOS. Adopted
       during the ENG003 re-seal ceremony after CI runners on Linux surfaced
       false CONFIG_DRIFT on unchanged source files.
       Operator authorization for the version bump: recorded in the commit
       message that ships this file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ALGORITHM_VERSION: int = 2


def _sha256_file(path: Path) -> str:
    """SHA-256 of a file's content, with CRLF → LF line-ending normalization.

    Algorithm v2 (see module docstring). The full file is read into memory,
    `\\r\\n` sequences are replaced by `\\n`, and the resulting byte stream is
    hashed. This is safe for the baseline files in scope (max ~30 KiB each).

    Rationale: MON001 must track CONTENT drift, not platform artefacts.
    """
    with path.open("rb") as f:
        raw = f.read()
    normalized = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def compute_fingerprint(repo_root: Path, baseline_files: list[str],
                        baseline_constants: dict) -> dict:
    """Return a dict describing the current production fingerprint.

    - `algorithm_version`: currently `2` — LF-normalized file bytes.
    - `files`: {path: sha256} for every baseline file (relative to repo_root).
    - `constants`: canonical JSON of the sealed baseline constants dict.
    - `hash`: SHA-256 of the JSON-serialization of
              {algorithm_version, files, constants}.

    Callers compare `hash` against the sealed hash. Any difference is CONFIG_DRIFT.
    Callers may additionally verify that `algorithm_version` matches the sealed
    algorithm version — a mismatch there indicates a governance event (re-seal
    ceremony) rather than a content drift.
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
        {
            "algorithm_version": ALGORITHM_VERSION,
            "files": files_hashes,
            "constants": canonical_constants,
        },
        sort_keys=True, ensure_ascii=False,
    )
    return {
        "algorithm_version": ALGORITHM_VERSION,
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
    # Algorithm-version drift is a governance event, not a content event
    curr_v = current_fp.get("algorithm_version")
    seal_v = sealed_fp.get("algorithm_version")
    if seal_v is not None and curr_v != seal_v:
        lines.append(
            f"  ALGORITHM_VERSION differs: sealed v{seal_v}, current v{curr_v} — "
            "this is a governance event (re-seal ceremony). "
            "See docs/CHANGE_CONTROL_CHECKLIST.md §3.")
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

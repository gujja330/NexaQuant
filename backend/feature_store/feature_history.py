"""Feature Store history — read/write parquet snapshots + manifest.

Layout:
  features/india/YYYY-MM-DD.parquet              canonical · authoritative
  features/india/YYYY-MM-DD.rebuilt_HHMMSS.parquet   candidate · never served
  features/india/YYYY-MM-DD.superseded_<UTC>.parquet archived by a promotion
  features/manifest.jsonl                        (append-only ledger)

Every write appends to the manifest with schema fingerprint + row count
+ timestamp. Reads are by (market, date) → DataFrame or None.

SNAPSHOT AUTHORITY · CEO 2026-11-04
-----------------------------------
The canonical `features/<market>/<asof>.parquet` is THE snapshot for that
market and date. Nothing else is served.

This reader used to do the opposite. It preferred the newest
`.rebuilt_*` sibling on the reasoning that it was "the freshest
computation", with the canonical file "preserved for provenance". The
consequence was that the 2026-11-03 snapshots could be rebuilt,
validated against every acceptance check, copied into place and
hash-verified — and still not be read by anything. Scoring was served
`2026-11-03.rebuilt_073223.parquet` (India) and `.rebuilt_073239`
(USA), neither of which any operator had promoted, and both of which
carried `macro_move` resolved from an undated snapshot under a
historical asof.

So: a rebuild is a CANDIDATE. Promotion is explicit, validated and
reversible (`promote_candidate`). A missing canonical file is an
explicit MISSING, never a silent fallback to a neighbour. And every read
reports the path and hash it actually served, because a bare DataFrame
cannot tell a caller which file produced it — which is precisely how the
substitution went unnoticed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd


FEATURES_ROOT = "features"          # relative to repo root
MANIFEST_NAME = "manifest.jsonl"

#: Status values a snapshot read can return.
SNAPSHOT_SERVED = "SERVED"       # the canonical file for this exact asof
SNAPSHOT_MISSING = "MISSING"     # no canonical file for this asof


def snapshot_path(repo_root: Path, market: str, asof: date) -> Path:
    return Path(repo_root) / FEATURES_ROOT / market / f"{asof.isoformat()}.parquet"


def manifest_path(repo_root: Path) -> Path:
    return Path(repo_root) / FEATURES_ROOT / MANIFEST_NAME


def write_snapshot(repo_root: Path, market: str, asof: date, df: pd.DataFrame) -> Path:
    """Write a snapshot without ever clobbering an existing canonical file.

    A second write for the same asof lands as a `.rebuilt_HHMMSS.parquet`
    CANDIDATE beside the canonical one. Candidates are not served — see
    the module docstring — so producing one changes nothing until someone
    promotes it.
    """
    p = snapshot_path(repo_root, market, asof)
    p.parent.mkdir(parents=True, exist_ok=True)
    # DO NOT overwrite an existing snapshot silently — write a stamped variant instead.
    if p.exists():
        # The original stays canonical. This is a candidate, and the
        # reader will not pick it up on its own.
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        p_new = p.with_suffix(f".rebuilt_{stamp}.parquet")
        df.to_parquet(p_new, index=False)
        return p_new
    df.to_parquet(p, index=False)
    return p


@dataclass(frozen=True)
class SnapshotRead:
    """The result of a snapshot read, with its provenance attached."""
    market: str
    asof: date
    status: str
    path: Optional[Path] = None
    sha256: Optional[str] = None
    n_rows: int = 0
    frame: Optional[pd.DataFrame] = None
    candidates: tuple = ()
    undated_features: tuple = ()
    reason: Optional[str] = None

    @property
    def served(self) -> bool:
        return self.status == SNAPSHOT_SERVED


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rebuild_candidates(repo_root: Path, market: str, asof: date) -> list[Path]:
    """The `.rebuilt_HHMMSS` siblings for one asof, oldest first.

    Preserved rather than deleted: each is the only surviving record of
    what one intraday rebuild computed.
    """
    p = snapshot_path(repo_root, market, asof)
    base = p.parent
    if not base.exists():
        return []
    return sorted(base.glob("%s.rebuilt_*.parquet" % p.stem))


def undated_features_present(df: pd.DataFrame) -> tuple:
    """Features in this frame that carry no observation date by construction.

    A snapshot built while its asof was TODAY may legitimately have
    resolved these from an undated current snapshot. Read back after that
    date, the same cell is lookahead: a value with no observation date
    standing under a historical asof. The file cannot be repaired after
    the fact, so the read reports it rather than trusting it.
    """
    try:
        from backend.feature_store.macro_series import SUMMARY_SYMBOL
    except Exception:
        return ()
    out = []
    for feat in sorted(SUMMARY_SYMBOL):
        if feat in df.columns and df[feat].notna().any():
            out.append(feat)
    return tuple(out)


def read_snapshot_detail(repo_root: Path, market: str,
                         asof: date) -> SnapshotRead:
    """Read the CANONICAL snapshot for this exact (market, asof).

    Never falls back to a `.rebuilt_*` candidate and never to a
    neighbouring date. See the module docstring for why.
    """
    p = snapshot_path(repo_root, market, asof)
    cands = tuple(rebuild_candidates(repo_root, market, asof))
    if not p.exists():
        return SnapshotRead(
            market=market, asof=asof, status=SNAPSHOT_MISSING,
            candidates=cands,
            reason=("no canonical snapshot at %s · %d rebuild candidate(s) "
                    "exist and are NOT served implicitly · promote one "
                    "explicitly if it is the intended snapshot"
                    % (p.as_posix(), len(cands))))
    df = pd.read_parquet(p)
    return SnapshotRead(
        market=market, asof=asof, status=SNAPSHOT_SERVED, path=p,
        sha256=_sha256(p), n_rows=int(len(df)), frame=df, candidates=cands,
        undated_features=undated_features_present(df))


def read_snapshot(repo_root: Path, market: str, asof: date) -> pd.DataFrame | None:
    """Canonical snapshot for (market, asof), or None if there is none.

    Thin wrapper over `read_snapshot_detail` so existing callers keep
    working unchanged. Use the detail form when provenance matters.
    """
    r = read_snapshot_detail(repo_root, market, asof)
    return r.frame if r.served else None


def promote_candidate(repo_root: Path, market: str, asof: date,
                      candidate: Path, validator=None) -> dict:
    """Make a rebuild candidate the canonical snapshot, explicitly.

    The prior canonical file is never destroyed — it is archived beside
    the snapshot as `<asof>.superseded_<UTC>.parquet` — so a promotion is
    reversible and the lineage stays on disk.

    `validator(df) -> (ok, reason)` runs before anything moves. A
    candidate that fails it is REFUSED and nothing is touched.
    """
    candidate = Path(candidate)
    if not candidate.exists():
        return {"state": "FAILED",
                "reason": "candidate does not exist: %s" % candidate.as_posix()}
    df = pd.read_parquet(candidate)
    if validator is not None:
        ok, why = validator(df)
        if not ok:
            return {"state": "REFUSED", "reason": why,
                    "candidate": candidate.as_posix()}
    target = snapshot_path(repo_root, market, asof)
    target.parent.mkdir(parents=True, exist_ok=True)
    archived = None
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archived = target.with_suffix(".superseded_%s.parquet" % stamp)
        target.replace(archived)
    tmp = target.with_suffix(".promoting.parquet")
    df.to_parquet(tmp, index=False)
    tmp.replace(target)
    return {"state": "PROMOTED", "market": market, "asof": asof.isoformat(),
            "candidate": candidate.as_posix(), "path": target.as_posix(),
            "sha256": _sha256(target), "n_rows": int(len(df)),
            "superseded": archived.as_posix() if archived else None}


def list_snapshots(repo_root: Path, market: str) -> list[date]:
    """Canonical snapshot dates only — candidates and archives excluded."""
    base = Path(repo_root) / FEATURES_ROOT / market
    if not base.exists():
        return []
    dates: list[date] = []
    for f in base.glob("*.parquet"):
        if (".rebuilt" in f.name or ".superseded" in f.name
                or ".promoting" in f.name):
            continue
        try:
            dates.append(date.fromisoformat(f.stem))
        except ValueError:
            continue
    return sorted(dates)


def append_manifest(repo_root: Path, entry: dict) -> None:
    p = manifest_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")

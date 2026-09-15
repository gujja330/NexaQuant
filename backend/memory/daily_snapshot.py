"""AEGIS historical memory: record what was actually known, on the day.

WHY THIS EXISTS
---------------
The 2026-09-15 PIT gate established that AEGIS is history-starved backward and
can only enrich forward. India gained +0 usable replay dates from the substrate
remediation because git holds no record of what AEGIS was scoring before
2026-06-19, and fundamentals exist only as one undated cross-section. That
ceiling cannot be lifted retroactively.

This module stops the ceiling from repeating. Each production/research day it
seals an immutable, provenanced record of the information state R2 actually
used, so a future replay can reconstruct WHAT WAS KNOWN THEN rather than
inferring it from WHAT IS KNOWN NOW.

CONTRACT (Part F)
-----------------
    NO SNAPSHOT   -> NO HISTORICAL EVIDENCE
    NO PROVENANCE -> PIT_BLOCKED
    CURRENT DATA  -> NEVER AUTOMATICALLY HISTORICAL

A family is never recorded as PIT-valid merely because an `asof` was supplied.
`observation_date`, `publication_date`, `effective_date`, `ingestion_date` and
`asof` are stored as distinct fields and are never collapsed.

IMMUTABILITY (Part E)
---------------------
A sealed day is never overwritten. If a source later revises history, the new
version lands under `revisions/` with its own timestamp, and the original stays
byte-intact so backtests can tell the two apart.

This module has NO production callers. It reads; it never mutates any
production artifact.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

# v2 (2026-09-15): the snapshot persists the CONSUMED matrices as parquet
# sidecars (technical_features, r2_scores, decisions) whose hashes enter the
# seal, and adds the r2_scores family. v1 stored only a description of the
# features, which is not the features.
SCHEMA_VERSION = "aegis.memory.daily.v2"
ROOT_DIRNAME = "history"

PIT_OK = "PIT_OK"
PIT_BLOCKED = "PIT_BLOCKED"
PIT_PARTIAL = "PIT_PARTIAL"


# ── provenance ────────────────────────────────────────────────────────
@dataclass
class Provenance:
    """Part D. Every family carries all of this or it is PIT_BLOCKED."""
    family: str
    source: str
    pit_status: str
    observation_date: Optional[str] = None   # when the value was measured
    publication_date: Optional[str] = None   # when it became knowable
    effective_date: Optional[str] = None     # the period it describes
    ingestion_date: Optional[str] = None     # when AEGIS first held it
    asof: Optional[str] = None               # the cutoff being recorded
    source_timestamp: Optional[str] = None
    retrieval_timestamp: Optional[str] = None
    revision_status: str = "ORIGINAL"
    schema_fingerprint: Optional[str] = None
    config_fingerprint: Optional[str] = None
    blocked_reason: Optional[str] = None
    n_records: int = 0

    def validate(self) -> list[str]:
        """A family may only claim PIT_OK if it can show a real date."""
        errs: list[str] = []
        if self.pit_status == PIT_OK:
            if not (self.observation_date or self.publication_date
                    or self.effective_date):
                errs.append(
                    "%s claims PIT_OK with no observation/publication/effective "
                    "date — an asof alone never confers PIT validity" % self.family)
            if not self.source:
                errs.append("%s claims PIT_OK with no source" % self.family)
        if self.pit_status == PIT_BLOCKED and not self.blocked_reason:
            errs.append("%s is PIT_BLOCKED without a stated reason" % self.family)
        return errs


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _write(p: Path, text: str) -> None:
    """Always write LF.

    A seal stores the sha256 of snapshot.json's BYTES. Python's default
    text mode translates newlines per-platform, so the same snapshot would
    hash differently on Windows and Linux and every seal would fail to
    verify after a cross-platform checkout. `history/** -text` in
    .gitattributes keeps git from re-translating them.
    """
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── the snapshot ──────────────────────────────────────────────────────
@dataclass
class DailySnapshot:
    market: str
    asof: str
    schema_version: str = SCHEMA_VERSION
    sealed_utc: Optional[str] = None
    families: dict = field(default_factory=dict)      # family -> payload
    provenance: dict = field(default_factory=dict)    # family -> Provenance
    fingerprints: dict = field(default_factory=dict)
    sidecars: dict = field(default_factory=dict)   # filename -> sha256
    content_hash: Optional[str] = None
    _frames: dict = field(default_factory=dict, repr=False)   # filename -> DataFrame

    def attach_frame(self, filename: str, df) -> None:
        """Persist a real consumed matrix beside the manifest.

        A description of the features R2 used is not the features R2 used.
        These are written as parquet and their sha256 enters the seal, so the
        matrix is as tamper-evident as the manifest itself.
        """
        self._frames[filename] = df

    def add(self, prov: Provenance, payload: Any) -> None:
        errs = prov.validate()
        if errs:
            raise ValueError("provenance rejected: " + "; ".join(errs))
        self.families[prov.family] = payload
        self.provenance[prov.family] = asdict(prov)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "market": self.market,
            "asof": self.asof,
            "sealed_utc": self.sealed_utc,
            "fingerprints": self.fingerprints,
            "sidecars": self.sidecars,
            "provenance": self.provenance,
            "families": self.families,
        }


def snapshot_dir(root: Path, market: str, asof: str) -> Path:
    return Path(root) / ROOT_DIRNAME / market.lower() / asof


def is_sealed(root: Path, market: str, asof: str) -> bool:
    return (snapshot_dir(root, market, asof) / "SEALED").exists()


def seal(root: Path, snap: DailySnapshot, *, allow_revision: bool = False) -> Path:
    """Write the snapshot immutably.

    A sealed day is never overwritten. A second seal for the same day is
    refused unless `allow_revision`, in which case it is stored under
    `revisions/<utc-timestamp>/` with the original left byte-intact.
    """
    d = snapshot_dir(root, snap.market, snap.asof)
    now = datetime.now(timezone.utc)
    snap.sealed_utc = now.isoformat(timespec="seconds")
    # Sidecars are written first so their hashes are inside the manifest, and
    # the manifest hash is inside the seal. Tampering with a matrix therefore
    # breaks verification exactly as tampering with the manifest does.
    if snap._frames:
        d.mkdir(parents=True, exist_ok=True)
        existing = (d / "SEALED").exists()
        target = d
        if existing and allow_revision:
            target = d / "revisions" / now.strftime("%Y%m%dT%H%M%S.%fZ")
            target.mkdir(parents=True, exist_ok=True)
        for name, frame in snap._frames.items():
            fp = target / name
            frame.to_parquet(fp, index=False)
            snap.sidecars[name] = file_sha256(fp)
    body = snap.to_dict()
    snap.content_hash = sha256_of(body)
    body["content_hash"] = snap.content_hash

    if (d / "SEALED").exists():
        if not allow_revision:
            raise PermissionError(
                "%s/%s is already sealed; historical days are immutable. Pass "
                "allow_revision=True to record a revision instead." % (snap.market, snap.asof))
        prior = json.loads((d / "snapshot.json").read_text(encoding="utf-8"))
        # Second-resolution names collide when two revisions land in the same
        # second, silently losing one. Revision history must never be lossy.
        base = now.strftime("%Y%m%dT%H%M%S.%fZ")
        rev = d / "revisions" / base
        n = 1
        while rev.exists():
            rev = d / "revisions" / ("%s-%d" % (base, n))
            n += 1
        rev.mkdir(parents=True, exist_ok=False)
        body["revision_status"] = "REVISED"
        body["supersedes_content_hash"] = prior.get("content_hash")
        body["revision_utc"] = snap.sealed_utc
        _write(rev / "snapshot.json", json.dumps(body, indent=1, default=str))
        _append_revision_log(d, prior.get("content_hash"), snap.content_hash, snap.sealed_utc)
        return rev / "snapshot.json"

    d.mkdir(parents=True, exist_ok=True)
    p = d / "snapshot.json"
    _write(p, json.dumps(body, indent=1, default=str))
    _write(d / "SEALED", json.dumps({"sealed_utc": snap.sealed_utc,
                                     "content_hash": snap.content_hash,
                                     "file_sha256": file_sha256(p),
                                     "sidecars": snap.sidecars}, indent=1))
    return p


def _append_revision_log(d: Path, old_hash, new_hash, when) -> None:
    log = d / "revisions" / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"revision_utc": when, "original_content_hash": old_hash,
                             "revised_content_hash": new_hash}) + "\n")


def load(root: Path, market: str, asof: str) -> Optional[dict]:
    p = snapshot_dir(root, market, asof) / "snapshot.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def verify_seal(root: Path, market: str, asof: str) -> tuple[bool, str]:
    """Detect tampering: the sealed hash must still match the file on disk."""
    d = snapshot_dir(root, market, asof)
    p, s = d / "snapshot.json", d / "SEALED"
    if not (p.exists() and s.exists()):
        return False, "not sealed"
    meta = json.loads(s.read_text(encoding="utf-8"))
    if file_sha256(p) != meta.get("file_sha256"):
        return False, "TAMPERED: snapshot.json no longer matches its seal"
    for name, sha in (meta.get("sidecars") or {}).items():
        sp = d / name
        if not sp.exists():
            return False, "MISSING SIDECAR: %s" % name
        if file_sha256(sp) != sha:
            return False, "TAMPERED: %s no longer matches its seal" % name
    return True, "ok"


# ── the daily contract (Part F) ───────────────────────────────────────
REQUIRED_FAMILIES = (
    "universe", "sector", "market_cap", "prices", "technical",
    "fundamentals", "earnings", "macro", "intermarket",
    "r2_config", "r2_scores", "r2_decision",
)


def check_contract(snap_dict: dict) -> dict:
    """Machine-checkable. Missing family -> NO HISTORICAL EVIDENCE.
    Family without provenance -> PIT_BLOCKED."""
    prov = snap_dict.get("provenance", {})
    missing = [f for f in REQUIRED_FAMILIES if f not in prov]
    blocked, ok, partial, invalid = [], [], [], []
    for fam, p in prov.items():
        status = p.get("pit_status")
        pv = Provenance(**{k: v for k, v in p.items()
                           if k in Provenance.__dataclass_fields__})
        errs = pv.validate()
        if errs:
            invalid.append({"family": fam, "errors": errs})
        if status == PIT_OK:
            ok.append(fam)
        elif status == PIT_PARTIAL:
            partial.append(fam)
        else:
            blocked.append(fam)
    return {
        "complete": not missing,
        "missing_families": missing,
        "pit_ok": sorted(ok),
        "pit_partial": sorted(partial),
        "pit_blocked": sorted(blocked),
        "provenance_violations": invalid,
        "verdict": "NO_HISTORICAL_EVIDENCE" if missing else
                   ("PROVENANCE_VIOLATION" if invalid else "CONTRACT_MET"),
    }


# ── evidence certification (memory must fail LOUDLY, not silently) ────
#
# Production delivery and historical evidence are separate concerns. A memory
# failure must never stop today's XLSX or Telegram — but it must also never
# pass unnoticed, because the failure mode it guards against is precisely
# "the clock reads zero forever and nothing says so".
#
#   MEMORY FAILURE -> production R2 may still run
#                  -> EVIDENCE CERTIFICATION = BLOCKED
#                  -> no historical research claim may be made for that day

MEMORY_CERT_OK = "EVIDENCE_CERTIFIED"
MEMORY_CERT_BLOCKED = "EVIDENCE_BLOCKED"


def certification_path(root: Path, market: str) -> Path:
    return Path(root) / "reports" / "context" / ("memory_certification_%s.json" % market.lower())


def write_certification(root: Path, market: str, asof: str, result: dict) -> Path:
    """Persist the outcome of the day's memory step, pass or fail."""
    status = result.get("status")
    certified = status in ("SEALED", "ALREADY_SEALED")
    body = {
        "schema_version": "aegis.memory.certification.v1",
        "market": market.lower(),
        "asof": asof,
        "memory_status": status,
        "evidence_certification": MEMORY_CERT_OK if certified else MEMORY_CERT_BLOCKED,
        "detail": result,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("production delivery is unaffected by this result; only the "
                 "right to make a historical evidence claim for this date is"),
    }
    p = certification_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write(p, json.dumps(body, indent=1))
    return p


def check_evidence_certified(root: Path, market: str, asof: str) -> tuple[bool, str]:
    """Gate for anything that wants to treat a date as historical evidence.

    Returns (certified, reason). A missing certification is BLOCKED, not a
    pass: absence of evidence about the memory step is not evidence that it ran.
    """
    p = certification_path(root, market)
    if not p.exists():
        return False, "no memory certification for %s; the day was never recorded" % market
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return False, "memory certification unreadable: %s" % e
    if d.get("asof") != asof:
        return False, ("memory certification covers %s, not %s"
                       % (d.get("asof"), asof))
    if d.get("evidence_certification") != MEMORY_CERT_OK:
        return False, ("memory step reported %s for %s"
                       % (d.get("memory_status"), asof))
    if not is_sealed(root, market, asof):
        return False, "certification claims sealed but no SEALED marker exists"
    ok, msg = verify_seal(root, market, asof)
    if not ok:
        return False, "seal verification failed: %s" % msg
    return True, "evidence certified for %s %s" % (market, asof)

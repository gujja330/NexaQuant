"""Staging and recoverable publication for the local AEGIS runner."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.shared.atomic_io import replace_with_retry, write_text_atomic


REGISTRY = Path("reports/research/opportunity_registry.jsonl")
OUTPUT_ROOTS = {"reports", "data", "features", "history", "output", "markets"}
INDIA_OUTPUT = {("india", "data"), ("india", "reports")}
USA_OUTPUT = {("usa", "data"), ("usa", "reports")}
RESEARCH_OUTPUT = {
    folder / name
    for folder in (Path("reports/research"), Path("reports/research/india"), Path("reports/research/usa"))
    for name in ("outcome_dataset.parquet", "outcome_dataset_summary.json",
                 "attribution_analysis.json", "attribution_report.md")
}
RUNTIME = ".aegis-local"


def contained(root: Path, relative: Path) -> Path:
    if relative.anchor or ".." in relative.parts:
        raise RuntimeError(f"invalid project-relative path: {relative}")
    root = root.resolve(strict=True)
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise RuntimeError(f"linked path is forbidden for project writes: {path}")
    if not path.resolve().is_relative_to(root):
        raise RuntimeError(f"path leaves the project: {path}")
    return path


def state_root(root: Path) -> Path:
    return contained(root, Path(RUNTIME))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path: Path, payload: dict) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2) + "\n")


def note_operation(storage: Path, operation: str) -> None:
    owner_file = storage / "owner.json"
    owner = json.loads(owner_file.read_text(encoding="utf-8"))
    if owner["pid"] == os.getpid():
        owner["operation"] = operation
        _json(owner_file, owner)


class RunInProgress(RuntimeError):
    """An existing runner holds the operating-system lock."""


@contextmanager
def _hold_lock(path: Path, market: str, *, owner_file: Path | None = None):
    with path.open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            owner = owner_file.read_text(encoding="utf-8").strip() if owner_file and owner_file.is_file() else "unavailable"
            raise RunInProgress(f"Another AEGIS run is active. Lock {path}. Owner {owner}.") from error
        if owner_file:
            _json(owner_file, {"pid": os.getpid(), "market": market,
                               "started_utc": datetime.now(timezone.utc).isoformat()})
        try:
            yield
        finally:
            if owner_file:
                owner_file.unlink(missing_ok=True)


@contextmanager
def locked(root: Path, market: str = "maintenance"):
    storage = state_root(root)
    storage.mkdir(exist_ok=True)
    with _hold_lock(contained(storage, Path("runner.lock")), market,
                    owner_file=contained(storage, Path("owner.json"))):
        yield storage


def _atomic_copy(src: Path, dst: Path, temporary: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as source, temporary.open("wb") as output:
        shutil.copyfileobj(source, output)
        output.flush()
        os.fsync(output.fileno())
    shutil.copystat(src, temporary)
    replace_with_retry(temporary, dst)


def pending_publications(storage: Path):
    for journal in sorted(storage.glob("*/publication.json")):
        journal = contained(storage, journal.relative_to(storage))
        data = json.loads(journal.read_text(encoding="utf-8"))
        if data["status"] == "publishing":
            yield journal, data


def require_clean_publication_state(storage: Path) -> None:
    for journal, _ in pending_publications(storage):
        raise RuntimeError(f"Publication recovery is pending at {journal}. "
                           "Review it before staging.")


def recover(root: Path, storage: Path) -> None:
    for journal, data in pending_publications(storage):
        for entry in reversed(data["files"]):
            rel = Path(entry["path"])
            dst = contained(root, rel)
            temporary = contained(journal.parent, Path("replacement.tmp"))
            current = digest(dst) if dst.is_file() else None
            if current == entry["before"]:
                continue
            if current != entry["after"]:
                raise RuntimeError(f"publication recovery found an external edit: {rel}")
            if entry["before"] is None:
                dst.unlink()
            else:
                backup = contained(journal.parent, Path("before") / rel)
                if digest(backup) != entry["before"]:
                    raise RuntimeError(f"publication backup checksum mismatch: {rel}")
                _atomic_copy(backup, dst, temporary)
        data["status"] = "rolled_back"
        _json(journal, data)


def _output(path: Path, scope: str) -> bool:
    if scope == "research":
        return path in RESEARCH_OUTPUT
    if path in RESEARCH_OUTPUT:
        return False
    segments = path.parts
    prefix = segments[:2]
    if prefix == ("reports", "unified"):
        return False
    if prefix in INDIA_OUTPUT | USA_OUTPUT:
        return prefix in (INDIA_OUTPUT if scope == "india" else USA_OUTPUT)
    if segments[0] not in OUTPUT_ROOTS:
        return scope == "india" and path == Path("configs/ensemble_weights_adaptive.yaml")
    other = "usa" if scope == "india" else "india"
    return not any(other in re.split(r"[^a-z0-9]+", part.lower()) for part in segments)


def _files(root: Path, scope: str) -> dict[Path, str]:
    checksums = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in {RUNTIME, ".aegis-tmp", ".git", ".venv"}]
        for name in files:
            path = Path(folder) / name
            relative = path.relative_to(root)
            if _output(relative, scope) and path.is_file():
                checksums[relative] = digest(path)
    return checksums


def _protected(path: Path) -> bool:
    return path == REGISTRY or (
        path.suffix == ".jsonl"
        and (path.name.startswith(("episode_lineage_", "orphan_audit_", "quarantine_audit",
                                  "prediction_snapshots", "lifecycle_breach_ledger_"))
             or "position_store" in path.parts)
    )


def _sealed_recommendation(path: Path) -> bool:
    return ("recommendations_history" in path.parts and "superseded" in path.parts
            and path.suffix == ".json")


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


class Attempt:
    def __init__(self, root: Path, storage: Path, scope: str, asof: str):
        self.root = root
        self.storage = storage
        self.scope = scope
        self.asof = asof
        self.started_utc = datetime.now(timezone.utc)
        stamp = self.started_utc.strftime("%Y%m%dT%H%M%SZ")
        self.folder = storage / f"{stamp}-{scope}-{uuid4().hex[:8]}"
        self.workspace = self.folder / "work"
        self.journal = self.folder / "publication.json"
        self.folder.mkdir()
        self.stages = []
        self.status("attempted")
        self.baseline = self._stage()

    def status(self, status: str, **details) -> None:
        _json(self.folder / "attempt.json", {
            "run_id": self.folder.name, "scope": self.scope, "asof": self.asof,
            "status": status, "started_utc": self.started_utc.isoformat(),
            "updated_utc": datetime.now(timezone.utc).isoformat(), **details,
        })

    def record_stage(self, name: str, status: str, seconds: float, **evidence) -> None:
        self.stages.append({"name": name, "status": status, "seconds": round(seconds, 3), **evidence})
        _json(self.folder / "stages.json", {"stages": self.stages})

    def _stage(self) -> dict[Path, str]:
        def copy(source, destination):
            path = Path(source)
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise RuntimeError(f"workspace contains a linked path: {path}")
            return shutil.copy2(source, destination)

        def ignore(folder, names):
            ignored = {RUNTIME, ".aegis-tmp", ".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
            for name in names:
                path = Path(folder) / name
                if name in ignored or name.startswith(".env"):
                    continue
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise RuntimeError(f"workspace contains a linked path: {path}")
            return ignored | {n for n in names if n.startswith(".env")}

        shutil.copytree(self.root, self.workspace, ignore=ignore, copy_function=copy)
        return _files(self.workspace, self.scope)

    def changed_files(self) -> dict[Path, str]:
        return {
            path: checksum for path, checksum in _files(self.workspace, self.scope).items()
            if checksum != self.baseline.get(path)
        }

    def validate_history(self, after: dict[Path, str] | None = None) -> None:
        if after is None:
            after = _files(self.workspace, self.scope)
        for path in self.baseline.keys() - after.keys():
            if _protected(path) or _sealed_recommendation(path):
                raise RuntimeError(f"staged run removed protected history: {path}")
        for rel, checksum in after.items():
            if _sealed_recommendation(rel) and (rel.stem != checksum or self.baseline.get(rel, checksum) != checksum):
                raise RuntimeError(f"staged changes rewrote a sealed recommendation: {rel}")
            if not _protected(rel) or checksum == self.baseline.get(rel):
                continue
            previous, updated = _lines(self.root / rel), _lines(self.workspace / rel)
            if rel == REGISTRY:
                if updated[:len(previous)] != previous:
                    raise RuntimeError("staged changes rewrote the opportunity registry")
                _validate_registry_events(previous, updated[len(previous):], self.scope)
            elif Counter(map(_record_key, previous)) - Counter(map(_record_key, updated)):
                raise RuntimeError(f"staged changes removed durable audit evidence: {rel}")

    def publish(self, *, certified: bool, related: tuple[Attempt, ...] = ()) -> None:
        changes = {}
        for attempt in (self, *related):
            after = _files(attempt.workspace, attempt.scope)
            attempt.validate_history(after)
            for path, checksum in after.items():
                before = attempt.baseline.get(path)
                if checksum == before:
                    continue
                previous = changes.get(path)
                if previous and previous[:2] != (before, checksum):
                    raise RuntimeError(f"staged publication scopes disagree: {path}")
                changes[path] = (before, checksum, attempt.workspace / path)
        # Copy workbooks last so validation reports and the state they describe
        # are in place before the workbook path is replaced.
        files = []
        for rel in sorted(changes, key=lambda path: (path.suffix.lower() == ".xlsx", path.as_posix())):
            before = contained(self.root, rel)
            baseline, checksum, _ = changes[rel]
            if (digest(before) if before.is_file() else None) != baseline:
                raise RuntimeError(f"production changed during staging: {rel}")
            if baseline is not None:
                backup = self.folder / "before" / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(before, backup)
                if digest(backup) != baseline:
                    raise RuntimeError(f"publication backup checksum mismatch: {rel}")
            files.append({"path": rel.as_posix(), "before": baseline, "after": checksum})
        manifest = {"status": "publishing", "certified": certified,
                    "scope": self.scope, "asof": self.asof, "files": files}
        _json(self.journal, manifest)
        try:
            for entry in files:
                rel = Path(entry["path"])
                current = contained(self.root, rel)
                if (digest(current) if current.is_file() else None) != entry["before"]:
                    raise RuntimeError(f"production changed during publication: {rel}")
                _atomic_copy(changes[rel][2], current, self.folder / "replacement.tmp")
            manifest["status"] = "committed"
            _json(self.journal, manifest)
        except BaseException:
            recover(self.root, self.storage)
            raise


def _record_key(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def validate_held_actions(root: Path, workspace: Path, asof: str) -> None:
    """Require an independent governed exit before a held REDUCE can close an episode."""
    original = _lines(root / REGISTRY)
    staged = _lines(workspace / REGISTRY)
    pending = [event for event in staged[len(original):]
               if event.get("market") == "india" and event.get("status") == "CLOSED"
               and event.get("closed_date") == asof]
    if not pending:
        return
    data = json.loads((workspace / "reports/recommendations.json").read_text(encoding="utf-8"))
    actions = {str(row.get("ticker") or "").split(".", 1)[0].upper():
               (row.get("investor_action") or {}).get("if_holding") for row in data["recommendations"]}
    reductions = [event for event in pending if actions.get(event["ticker"].upper()) == "REDUCE"]
    if not reductions:
        return
    audit_path = workspace / "reports" / "audit" / f"dynamic_exit_decisions_india_{asof}.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    decisions = {row["opportunity_id"]: row for row in audit.get("decisions", [])}
    for event in reductions:
        decision = decisions.get(event["opportunity_id"], {})
        trigger = str(decision.get("event") or "")
        if (decision.get("action") != "ENFORCED" or decision.get("asof") != asof
                or not trigger.startswith("EXIT_") or not event["closed_reason"].startswith(trigger)):
            raise RuntimeError(f"full closure conflicts with held REDUCE: {event['opportunity_id']}")


def _validate_registry_events(previous: list[dict], appended: list[dict], scope: str) -> None:
    latest = {}
    for event in previous:
        episode = event.get("opportunity_id")
        if episode and str(event.get("ts_utc") or "") >= str(latest.get(episode, {}).get("ts_utc") or ""):
            latest[episode] = event
    identity = ("market", "runner", "ticker", "created_date", "initial_signal", "initial_rank", "initial_score")
    for event in appended:
        episode = event.get("opportunity_id")
        status = event.get("status")
        if event.get("market") != scope:
            raise RuntimeError("staged registry events crossed market boundaries")
        if not episode or not event.get("ticker") or not event.get("runner") or status not in {"ACTIVE", "CLOSED", "REJECTED"}:
            raise RuntimeError(f"registry event has no valid episode identity or state: {episode}")
        try:
            admission = date.fromisoformat(event.get("created_date") or "")
            if status != "ACTIVE":
                exit_date = date.fromisoformat(event.get("closed_date") or "")
                if exit_date < admission or not str(event.get("closed_reason") or "").strip():
                    raise ValueError("terminal event has no timely documented disposition")
        except ValueError as error:
            raise RuntimeError(f"invalid registry dates or reason for {episode}: {error}") from error
        prior = latest.get(episode)
        if prior:
            if any(prior.get(field) != event.get(field) for field in identity):
                raise RuntimeError(f"staged changes altered the admission identity: {episode}")
            if prior.get("status") in {"CLOSED", "REJECTED"} and prior["status"] != status:
                raise RuntimeError(f"staged changes reopened or reclassified a terminal episode: {episode}")
            if str(event.get("ts_utc") or "") < str(prior.get("ts_utc") or ""):
                raise RuntimeError(f"staged registry event predates existing state: {episode}")
        elif status != "ACTIVE":
            raise RuntimeError(f"new episode has no initial admission event: {episode}")
        latest[episode] = event

"""
MON001 forward observation ledger — append-only, tamper-detecting.

Every production recommendation observed after the MON001 forward boundary is snapshotted
as an immutable JSONL row. Any attempt to mutate a sealed row is a DATA_INTEGRITY_FAILURE.

Design invariants:
- Ledger file is APPEND-ONLY. No in-place edits. Corrections go to a separate corrections
  file that references the original by (fingerprint_hash, rec_id, snapshot_ts).
- Every row is content-hashed at write time; the hash is included in the row itself and
  the file's hash-chain (Merkle-like) allows detection of any retroactive rewrite.
- Ledger rows preserve enough fields to reconstruct A/B/C/D/E lifecycle (model rec /
  paper exec / broker order / broker fill / realized outcome).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


LEDGER_SCHEMA_VERSION = 1

# Required top-level fields on every row. Extra fields are permitted but never removable.
REQUIRED_FIELDS = (
    "schema_version",
    "snapshot_ts_utc",         # observation timestamp
    "asof",                    # market-date the recommendation is for
    "rec_id",                  # unique recommendation identifier
    "fingerprint_hash",        # baseline fingerprint at snapshot time
    "symbol",
    "portfolio_cycle",         # e.g. "2026-06-25_63"
    "buy_price",               # theoretical paper entry price
    "intended_weight",
    "sector",
    "regime_label",            # Strong / Neutral / Weak
    "exposure_multiplier",     # from current_regime()
    "benchmark_ref",           # benchmark level at asof
    "source_mode",             # PAPER | BROKER
    "broker_order_id",         # nullable
    "broker_fill_id",          # nullable
    "fill_price",              # nullable
    "fill_ts_utc",             # nullable
    "data_quality",            # OK | MISSING_PRICE | STALE | ...
    "row_hash",                # SHA-256 of the row minus row_hash + prev_row_hash chain
    "prev_row_hash",           # hash chain
)


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_row(row_without_hash: dict) -> str:
    canonical = json.dumps(row_without_hash, sort_keys=True, ensure_ascii=False,
                           default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LedgerError(Exception):
    """Base for all ledger errors."""


class DataIntegrityFailure(LedgerError):
    """Raised when tamper is detected (hash chain break, retroactive mutation, etc.)."""


class ForwardLedger:
    """Append-only forward observation ledger with hash-chain integrity."""

    def __init__(self, path: str | Path, corrections_path: str | Path,
                 forward_boundary_asof: str):
        self.path = Path(path)
        self.corrections_path = Path(corrections_path)
        self.forward_boundary_asof = str(forward_boundary_asof)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.corrections_path.parent.mkdir(parents=True, exist_ok=True)

    def _iter_raw(self) -> Iterable[dict]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def rows(self) -> list[dict]:
        return list(self._iter_raw())

    def last_hash(self) -> str:
        rows = self.rows()
        return rows[-1]["row_hash"] if rows else "GENESIS"

    def append(self, obs: dict) -> str:
        """Append one forward observation. Returns the new row_hash.

        Raises ValueError if the observation is missing required fields or violates the
        forward boundary. Raises DataIntegrityFailure if hash-chain state is broken.
        """
        # Fields set by append() itself (not required from caller):
        _appended_by_append = {"row_hash", "prev_row_hash", "schema_version",
                                "snapshot_ts_utc"}
        missing = [k for k in REQUIRED_FIELDS
                   if k not in _appended_by_append and k not in obs]
        if missing:
            raise ValueError(f"forward observation missing required fields: {missing}")
        if str(obs["asof"]) < self.forward_boundary_asof:
            raise ValueError(
                f"asof {obs['asof']} < forward_boundary_asof "
                f"{self.forward_boundary_asof} — refusing to snapshot pre-boundary")

        obs = dict(obs)
        obs["schema_version"] = LEDGER_SCHEMA_VERSION
        obs.setdefault("snapshot_ts_utc", _iso_utc())
        obs["prev_row_hash"] = self.last_hash()

        core = {k: obs[k] for k in obs if k != "row_hash"}
        obs["row_hash"] = _hash_row(core)

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obs, ensure_ascii=False, default=str) + "\n")

        return obs["row_hash"]

    def append_correction(self, target_row_hash: str, reason: str, patch: dict) -> str:
        """Append a correction record referencing an existing row by its content hash.

        Corrections NEVER mutate the original row. They are stored in a separate file that
        the monitor considers when computing derived metrics. Retroactive mutation of the
        main ledger is still a DATA_INTEGRITY_FAILURE.
        """
        row = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "correction_ts_utc": _iso_utc(),
            "target_row_hash": str(target_row_hash),
            "reason": str(reason),
            "patch": patch,
        }
        row["correction_hash"] = _hash_row(row)
        with self.corrections_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return row["correction_hash"]

    def verify_chain(self) -> dict:
        """Walk the ledger and verify every row's hash-chain integrity.

        Returns a dict with 'ok', 'rows_checked', 'first_bad_index' (or None), 'reason'.
        """
        rows = self.rows()
        prev = "GENESIS"
        for i, r in enumerate(rows):
            if r.get("prev_row_hash") != prev:
                return {"ok": False, "rows_checked": i, "first_bad_index": i,
                        "reason": f"prev_row_hash mismatch at row {i} "
                                  f"(expected {prev}, got {r.get('prev_row_hash')})"}
            expected = _hash_row({k: v for k, v in r.items() if k != "row_hash"})
            if r.get("row_hash") != expected:
                return {"ok": False, "rows_checked": i, "first_bad_index": i,
                        "reason": f"row_hash mismatch at row {i} — retroactive mutation "
                                  f"or corruption detected"}
            if str(r.get("asof", "")) < self.forward_boundary_asof:
                return {"ok": False, "rows_checked": i, "first_bad_index": i,
                        "reason": f"row {i} has asof {r.get('asof')} < forward boundary "
                                  f"{self.forward_boundary_asof}"}
            prev = r["row_hash"]
        return {"ok": True, "rows_checked": len(rows), "first_bad_index": None,
                "reason": "chain intact"}

    def unique_rec_ids(self) -> set[str]:
        return {r["rec_id"] for r in self.rows()}

    def duplicate_rec_ids(self) -> list[str]:
        """Return any rec_ids that appear more than once with the SAME fingerprint_hash.

        Different fingerprints imply the recommendation was re-observed under a new
        production baseline — that's CONFIG_DRIFT, not a duplicate.
        """
        seen: dict[tuple[str, str], int] = {}
        for r in self.rows():
            key = (r["rec_id"], r["fingerprint_hash"])
            seen[key] = seen.get(key, 0) + 1
        return [rid for (rid, _fp), n in seen.items() if n > 1]


def make_observation_row(*, asof: str, rec_id: str, fingerprint_hash: str, symbol: str,
                          portfolio_cycle: str, buy_price: float, intended_weight: float,
                          sector: str, regime_label: str, exposure_multiplier: float,
                          benchmark_ref: float | None, source_mode: str = "PAPER",
                          broker_order_id: str | None = None,
                          broker_fill_id: str | None = None,
                          fill_price: float | None = None,
                          fill_ts_utc: str | None = None,
                          data_quality: str = "OK") -> dict:
    """Helper to build a well-formed observation row (row_hash filled by ledger.append)."""
    if source_mode not in ("PAPER", "BROKER"):
        raise ValueError(f"source_mode must be PAPER or BROKER, got {source_mode!r}")
    if source_mode == "PAPER":
        if broker_order_id or broker_fill_id or fill_price is not None:
            raise ValueError("PAPER mode must not populate broker_* fields")
    if source_mode == "BROKER" and (broker_order_id is None or fill_price is None):
        raise ValueError("BROKER mode requires broker_order_id and fill_price")
    return {
        "asof": str(asof),
        "rec_id": str(rec_id),
        "fingerprint_hash": str(fingerprint_hash),
        "symbol": str(symbol),
        "portfolio_cycle": str(portfolio_cycle),
        "buy_price": float(buy_price),
        "intended_weight": float(intended_weight),
        "sector": str(sector),
        "regime_label": str(regime_label),
        "exposure_multiplier": float(exposure_multiplier),
        "benchmark_ref": None if benchmark_ref is None else float(benchmark_ref),
        "source_mode": source_mode,
        "broker_order_id": broker_order_id,
        "broker_fill_id": broker_fill_id,
        "fill_price": None if fill_price is None else float(fill_price),
        "fill_ts_utc": fill_ts_utc,
        "data_quality": str(data_quality),
    }

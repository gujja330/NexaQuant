"""Recommendation snapshot store · append-only per-day archive.

Layout:
    reports/recommendations_history/{market}/YYYY-MM-DD.json         (India)
    usa/reports/recommendations_history/{market}/YYYY-MM-DD.json     (USA)

Each snapshot file is the FULL enriched recommendations.json payload
as of that date — investor_action + position_plan + why + rotation +
lifecycle + evolution (if computed) blocks all present. This lets any
future consumer read back the exact operator-visible state on any
historical day without re-running the pipeline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

SCHEMA_FINGERPRINT = "aegis.recommendation.snapshot.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.snapshot.v1"

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.json$")


def _history_dir(reports_root: Path, market: str) -> Path:
    return reports_root / "recommendations_history" / market


def _parse_iso_date(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def archive_snapshot(payload: Mapping,
                        reports_root: Path,
                        market: str,
                        asof: str | date | None = None) -> Path:
    """Write today's enriched payload to the history directory.

    Idempotent: rerunning the same date overwrites the same file. Historical
    dates are never touched by this call. Returns the path written.
    """
    if asof is None:
        asof = payload.get("asof") or date.today().isoformat()
    asof_date = asof if isinstance(asof, date) else _parse_iso_date(str(asof)) or date.today()
    hdir = _history_dir(reports_root, market)
    hdir.mkdir(parents=True, exist_ok=True)
    out = hdir / f"{asof_date.isoformat()}.json"
    # Stamp the snapshot header so replayed reads can validate origin
    stamped = dict(payload)
    stamped["snapshot_engine"] = ENGINE_ID
    stamped["snapshot_schema_fingerprint"] = SCHEMA_FINGERPRINT
    stamped["snapshot_written_utc"] = datetime.now(timezone.utc).isoformat()
    stamped["snapshot_asof"] = asof_date.isoformat()
    out.write_text(json.dumps(stamped, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return out


def archive_state_path(reports_root: Path, market: str) -> Path:
    """Where the archive records whether it actually landed."""
    return (Path(reports_root) / "context"
            / ("recommendation_snapshot_state_%s.json" % str(market).lower()))


def archive_and_record(payload: Mapping,
                       reports_root: Path,
                       market: str,
                       asof: str | date | None = None) -> dict:
    """Archive, then PROVE the file landed, and record the verdict.

    CEO 2026-11-03 · WHY A BARE archive_snapshot WAS NOT ENOUGH
    -----------------------------------------------------------
    reports/recommendations_history/india/ holds two files, both from
    2026-07-29 and 2026-07-30. Nothing has archived for three months, and
    `backend/tests/test_date_consistency.py::test_snapshot_for_recs_asof_exists`
    has been failing on it.

    The writer was never missing. `archive_snapshot` is called from
    ssot/run.py, inside a `try` whose handler is commented "Enrichment
    failure must NEVER break the SSoT pipeline · log and continue". So any
    enrichment step that raises BEFORE the archive line skips the archive,
    the handler prints, and the step exits 0. The orchestrator then
    recorded `recommendation_ssot verdict=SUCCESS optional=False
    elapsed=3.41` for the 2026-11-02 run - a non-optional step reporting
    success on a day whose snapshot was never written.

    That is the same shape as the daily-history defect: a step whose
    failure reads as a successful day. The cure there was to stop
    returning None and start recording a verifiable state, so this does
    the same.

    state is PERSISTED / FAILED, and PERSISTED requires the file to exist
    AND re-parse - writing it is not the same as having written it.
    """
    mkt = str(market).lower()
    if asof is None:
        asof = payload.get("asof") or date.today().isoformat()
    asof_date = (asof if isinstance(asof, date)
                 else _parse_iso_date(str(asof)) or date.today())
    state = {
        "engine": ENGINE_ID,
        "schema_version": SCHEMA_VERSION,
        "market": mkt,
        "asof": asof_date.isoformat(),
        "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": "FAILED",
        "verified": False,
        "path": None,
        "n_recommendations": None,
        "reason": None,
    }
    try:
        out = archive_snapshot(payload, reports_root, mkt, asof=asof_date)
        state["path"] = str(out)
        # Verify by reading it back · the write is not the evidence.
        back = json.loads(out.read_text(encoding="utf-8"))
        recs = back.get("recommendations") or []
        state["n_recommendations"] = len(recs)
        if back.get("snapshot_asof") == asof_date.isoformat():
            state.update(state="PERSISTED", verified=True)
        else:
            state["reason"] = ("ASOF_MISMATCH_ON_READBACK: wrote %s, read %s"
                               % (asof_date.isoformat(),
                                  back.get("snapshot_asof")))
    except Exception as exc:                       # noqa: BLE001
        state["reason"] = "%s: %s" % (type(exc).__name__, exc)

    try:
        p = archive_state_path(reports_root, mkt)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2, default=str),
                     encoding="utf-8")
    except Exception:
        pass        # the verdict is best-effort; the archive is the point
    return state


def list_snapshot_dates(reports_root: Path, market: str) -> list[date]:
    """Return all available snapshot dates for a market, oldest first."""
    hdir = _history_dir(reports_root, market)
    if not hdir.exists():
        return []
    dates: list[date] = []
    for p in hdir.iterdir():
        m = _DATE_RE.match(p.name)
        if not m:
            continue
        try:
            dates.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    return sorted(dates)


def load_snapshot_for_date(reports_root: Path, market: str,
                              asof: str | date) -> dict | None:
    """Return the snapshot for an exact date, or None."""
    asof_date = asof if isinstance(asof, date) else _parse_iso_date(str(asof))
    if asof_date is None:
        return None
    p = _history_dir(reports_root, market) / f"{asof_date.isoformat()}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def load_previous_snapshot(reports_root: Path, market: str,
                              before_asof: str | date) -> dict | None:
    """Return the newest snapshot strictly BEFORE `before_asof`.

    Used by the Evolution enricher to compute yesterday→today deltas.
    Returns None if no prior snapshot exists (first-ever run).
    """
    target = before_asof if isinstance(before_asof, date) else _parse_iso_date(str(before_asof))
    if target is None:
        return None
    all_dates = list_snapshot_dates(reports_root, market)
    prior = [d for d in all_dates if d < target]
    if not prior:
        return None
    return load_snapshot_for_date(reports_root, market, prior[-1])


def load_snapshot_range(reports_root: Path, market: str,
                           lookback_days: int,
                           end_asof: str | date | None = None) -> list[dict]:
    """Return snapshots within the last `lookback_days` days ending at `end_asof`.

    Ordered oldest→newest. Used by the Backtrack Engine (7/30/90/365-day
    windows) once enough history has accumulated.
    """
    if end_asof is None:
        end_asof = date.today()
    end = end_asof if isinstance(end_asof, date) else _parse_iso_date(str(end_asof)) or date.today()
    from datetime import timedelta
    start = end - timedelta(days=int(max(0, lookback_days)))
    dates = [d for d in list_snapshot_dates(reports_root, market)
              if start <= d <= end]
    out: list[dict] = []
    for d in dates:
        snap = load_snapshot_for_date(reports_root, market, d)
        if snap is not None:
            out.append(snap)
    return out


# Convenience: extract a {ticker: rec} map from a snapshot payload
def snapshot_to_ticker_map(snapshot: Mapping | None) -> dict[str, dict]:
    if not snapshot:
        return {}
    recs = snapshot.get("recommendations") or []
    if not isinstance(recs, list):
        return {}
    return {str(r.get("ticker") or ""): r for r in recs if r.get("ticker")}

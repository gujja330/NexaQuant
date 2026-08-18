"""AEGIS Opportunity Registry · persistent per-opportunity lifecycle store.

Operator directive 2026-08-18 (final architectural fix, Section 2-6):
  "AEGIS must stop treating 'today's recommendation' as a new opportunity.
   It needs a persistent Opportunity Registry."

Every unique investment idea gets ONE immutable record:

    IND-R1-ZYDUSLIFE-20260811-abc123    ← created once, never modified

That id persists across days. NEW is a lifecycle state that fires
exactly once (on the created_date). Re-entry after a genuine CLOSE
produces a NEW id · never re-uses the closed one.

Why this closes the recurring bugs
──────────────────────────────────
1. ZYDUSLIFE showing NEW on Aug 11, 12, 13, ..., 18 · because the row
   builder was computing NEW from the row's Recommended date which
   was itself being restamped to today. Registry lookup gives the
   ORIGINAL created_date every time · NEW fires only when
   created_date == today.

2. ONGC/HINDUNILVR restamping Recommended = today · registry never
   allows the created_date field to change.

3. INDIGO showing NEW + CLOSED same day · registry's opportunity
   status becomes REJECTED on that same day · downstream Portfolio
   NEW section filters status != REJECTED.

4. Re-entry ambiguity (LUPIN closed then attractive again) · new
   opportunity_id · original stays terminal · no id collision.

Storage
───────
`reports/research/opportunity_registry.jsonl`  (repo root · both markets)

  Append-only for creation events + status transitions. The full
  registry is rehydrated at pipeline start via `load_all()`. In-memory
  index is (market, runner, ticker) -> list-of-opportunities in
  temporal order · latest-status semantics.

Schema (one JSON object per line)
─────────────────────────────────
  opportunity_id     str    IND-R1-ZYDUSLIFE-20260811-abc123
  market             str    india | usa
  runner             str    R1 | R2 | R3
  ticker             str    ZYDUSLIFE (bare · no .NS/.BO)
  created_date       str    YYYY-MM-DD  · IMMUTABLE
  initial_signal     str    STRONG BUY | BUY | HOLD | ...
  initial_rank       int|None
  initial_score      float|None
  status             str    ACTIVE | CLOSED | REJECTED
  closed_date        str    YYYY-MM-DD  (empty while ACTIVE)
  closed_reason      str    STOP_LOSS_HIT | TARGET_REACHED | ROTATION | ...
  last_seen_date     str    updated each day the opportunity is still tracked
  ts_utc             str    creation/update timestamp (informational)

Constitutional invariants (validated at write-time)
──────────────────────────────────────────────────
· created_date NEVER changes for an existing opportunity_id
· status transitions are one-way: ACTIVE → CLOSED · ACTIVE → REJECTED
· CLOSED/REJECTED cannot revert to ACTIVE (re-entry requires new id)
· opportunity_id is a deterministic hash of (market, runner, ticker,
  created_date) so identical inputs regenerate identical ids
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────

@dataclass
class Opportunity:
    opportunity_id:  str = ""
    market:          str = ""
    runner:          str = ""
    ticker:          str = ""      # bare · no .NS/.BO
    created_date:    str = ""      # YYYY-MM-DD · IMMUTABLE
    initial_signal:  str = ""
    initial_rank:    int | None = None
    initial_score:   float | None = None
    status:          str = "ACTIVE"     # ACTIVE | CLOSED | REJECTED
    closed_date:     str = ""
    closed_reason:   str = ""
    last_seen_date:  str = ""
    ts_utc:          str = ""

    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    def is_terminal(self) -> bool:
        return self.status in ("CLOSED", "REJECTED")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _bare_ticker(t: str) -> str:
    return (t or "").upper().replace(".NS", "").replace(".BO", "")


def _mkt_tag(market: str) -> str:
    return "IND" if (market or "").lower() == "india" else "USA"


def make_opportunity_id(market: str, runner: str, ticker: str, created_date: str) -> str:
    """Deterministic id · same inputs = same id (idempotent)."""
    r = (runner or "").upper().replace("_NEW", "").strip()
    r_tag = r if r in ("R1", "R2", "R3") else "R?"
    tk = _bare_ticker(ticker)
    mkt = _mkt_tag(market)
    ds = (created_date or "")[:10].replace("-", "")
    sig = hashlib.sha256(f"{mkt}-{r_tag}-{tk}-{ds}".encode()).hexdigest()[:6]
    return f"{mkt}-{r_tag}-{tk}-{ds}-{sig}"


def _registry_path(root: Path) -> Path:
    return root / "reports" / "research" / "opportunity_registry.jsonl"


# ─────────────────────────────────────────────────────────────
# Load / Save
# ─────────────────────────────────────────────────────────────

def load_all(root: Path) -> dict:
    """Return {(market, runner, ticker): [Opportunity, ...]} in
    chronological order (event-sourced · last event per opportunity_id
    wins, so a CLOSED transition overrides the original ACTIVE creation
    record). Empty dict if registry file missing."""
    p = _registry_path(root)
    if not p.exists():
        return {}
    # First pass · collect ALL events keyed by opportunity_id · keep latest by ts_utc
    latest_by_id: dict = {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        opp = Opportunity(**{k: d.get(k) for k in Opportunity.__dataclass_fields__.keys()})
        oid = opp.opportunity_id or ""
        if not oid: continue
        prior = latest_by_id.get(oid)
        # Keep the record with the latest ts_utc (or first-seen if ts equal)
        if prior is None or str(opp.ts_utc) >= str(prior.ts_utc):
            latest_by_id[oid] = opp
    # Second pass · group by (market, runner, ticker) preserving chronological order
    out: dict = {}
    for opp in latest_by_id.values():
        key = (opp.market.lower(), opp.runner.upper(), _bare_ticker(opp.ticker))
        out.setdefault(key, []).append(opp)
    for k in out:
        out[k].sort(key=lambda o: (o.created_date, o.ts_utc))
    return out


def _append(root: Path, obj: dict) -> None:
    p = _registry_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, default=str, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def get_or_create(root: Path, market: str, runner: str, ticker: str,
                            asof: str, *,
                            initial_signal: str = "",
                            initial_rank: int | None = None,
                            initial_score: float | None = None,
                            registry: dict | None = None) -> Opportunity:
    """Return the ACTIVE opportunity for (market, runner, ticker), creating
    one if none exists. If an ACTIVE opportunity exists · returns it
    unchanged (created_date preserved). If only CLOSED/REJECTED exist ·
    creates a NEW re-entry opportunity with today's asof as created_date."""
    if registry is None:
        registry = load_all(root)
    market = market.lower()
    runner = (runner or "").upper().replace("_NEW", "")
    tk = _bare_ticker(ticker)
    key = (market, runner, tk)
    existing = registry.get(key, [])
    # If any existing is ACTIVE · return it (immutable created_date preserved)
    for opp in existing:
        if opp.is_active():
            return opp
    # No active · create new (either first-ever OR re-entry after CLOSE)
    opp = Opportunity(
        opportunity_id=make_opportunity_id(market, runner, tk, asof),
        market=market, runner=runner, ticker=tk,
        created_date=asof[:10],
        initial_signal=str(initial_signal or ""),
        initial_rank=initial_rank,
        initial_score=initial_score,
        status="ACTIVE",
        last_seen_date=asof[:10],
        ts_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _append(root, asdict(opp))
    registry.setdefault(key, []).append(opp)
    return opp


def close(root: Path, opportunity_id: str, asof: str, reason: str,
              registry: dict | None = None) -> Opportunity | None:
    """Transition an ACTIVE opportunity to CLOSED. Idempotent (already-
    CLOSED returns unchanged). Never reverses CLOSED → ACTIVE."""
    if registry is None:
        registry = load_all(root)
    for opps in registry.values():
        for opp in opps:
            if opp.opportunity_id == opportunity_id:
                if opp.status == "CLOSED":
                    return opp
                opp.status = "CLOSED"
                opp.closed_date = asof[:10]
                opp.closed_reason = str(reason or "")
                opp.last_seen_date = asof[:10]
                opp.ts_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                _append(root, asdict(opp))
                return opp
    return None


def reject(root: Path, opportunity_id: str, asof: str, reason: str,
                registry: dict | None = None) -> Opportunity | None:
    """Same-day-CLOSED case (INDIGO) · mark REJECTED instead of CLOSED
    so downstream NEW-section filter can drop it (a rejected candidate
    was never a real position)."""
    if registry is None:
        registry = load_all(root)
    for opps in registry.values():
        for opp in opps:
            if opp.opportunity_id == opportunity_id:
                if opp.status == "REJECTED":
                    return opp
                opp.status = "REJECTED"
                opp.closed_date = asof[:10]
                opp.closed_reason = str(reason or "")
                opp.last_seen_date = asof[:10]
                opp.ts_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                _append(root, asdict(opp))
                return opp
    return None


def touch(root: Path, opportunity_id: str, asof: str,
              registry: dict | None = None) -> Opportunity | None:
    """Update last_seen_date without mutating created_date or status.
    Idempotent per (opportunity_id, asof)."""
    if registry is None:
        registry = load_all(root)
    for opps in registry.values():
        for opp in opps:
            if opp.opportunity_id == opportunity_id:
                if opp.last_seen_date == asof[:10]:
                    return opp   # already touched today
                opp.last_seen_date = asof[:10]
                opp.ts_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                _append(root, asdict(opp))
                return opp
    return None


def lifecycle_state(opp: Opportunity, asof: str) -> str:
    """Client-facing lifecycle bucket for this opportunity + today's date:
        NEW      · asof == created_date (day 0 · fresh)
        ACTIVE   · asof > created_date and status == ACTIVE
        CLOSED   · status == CLOSED
        REJECTED · status == REJECTED
    """
    if opp.status == "CLOSED":
        return "CLOSED"
    if opp.status == "REJECTED":
        return "REJECTED"
    if opp.created_date == asof[:10]:
        return "NEW"
    return "ACTIVE"


def opportunity_age_days(opp: Opportunity, asof: str) -> int:
    """Trading-days-agnostic calendar age. Returns 0 on first day."""
    try:
        from datetime import date
        c = date.fromisoformat(opp.created_date)
        a = date.fromisoformat(asof[:10])
        return max(0, (a - c).days)
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────
# Bulk helpers for validators / diagnostic scripts
# ─────────────────────────────────────────────────────────────

def count_by_status(registry: dict) -> dict:
    counts: dict = {"ACTIVE": 0, "CLOSED": 0, "REJECTED": 0}
    for opps in registry.values():
        for opp in opps:
            counts[opp.status] = counts.get(opp.status, 0) + 1
    return counts


def opportunities_created_on(registry: dict, asof: str) -> list:
    return [opp for opps in registry.values() for opp in opps
                if opp.created_date == asof[:10]]


def opportunities_closed_on(registry: dict, asof: str) -> list:
    return [opp for opps in registry.values() for opp in opps
                if opp.closed_date == asof[:10]]


def active_opportunities(registry: dict) -> list:
    return [opp for opps in registry.values() for opp in opps if opp.is_active()]

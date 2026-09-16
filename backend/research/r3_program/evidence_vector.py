"""R3 evidence vector — one PIT-safe feature vector per (market, as_of, ticker).

    technical · fundamental · temporal · sector · peer · cross-sector
    macro · market-structure · exit · portfolio
            -> evidence vector -> replay -> OOS -> calibration
            -> economic value -> incremental R2 value

WHAT THIS MODULE IS FOR
-----------------------
Each family above has been investigated separately over this programme, and the
same question kept having to be rediscovered by hand: *is this family actually
available, PIT-safe, and deep enough at this date?* The answers are not stable —
they differ by market, by family, and by as_of.

So availability is computed and recorded, never assumed. A family that cannot
demonstrate point-in-time provenance is emitted as BLOCKED with a reason rather
than silently contributing nulls that later look like data.

THE RULE THAT GOVERNS EVERY FAMILY
----------------------------------
A value may enter the vector at `as_of` only if the moment it became knowable is
itself known and is <= as_of. Not the period it describes — the moment it became
knowable. Those differ by a median of 33 days in SEC filings and are unknown
entirely for India fundamentals, which is why the two markets score differently.

WHAT THIS MODULE IS NOT
-----------------------
It computes no predictions, trains nothing, and writes nothing to production.
R3 production writes remain 0.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.evidence_vector.v1"

# Availability states. Deliberately distinct: "we have no data" and "we have
# data but cannot prove when it was knowable" are different failures and need
# different remedies.
AVAILABLE = "AVAILABLE"                 # present and PIT-provable
PARTIAL = "PARTIAL"                     # present, provenance weaker than ideal
BLOCKED_PIT = "BLOCKED_PIT"             # present but no provable availability date
BLOCKED_DATA = "BLOCKED_DATA"           # not present at all
BLOCKED_DEPTH = "BLOCKED_DEPTH"         # present, PIT-safe, too shallow to use
REJECTED = "REJECTED"                   # tested and disposed of by prior research

FAMILIES = ("technical", "fundamental", "temporal", "sector", "peer",
            "cross_sector", "macro", "market_structure", "exit", "portfolio")


@dataclass
class FamilyStatus:
    family: str
    market: str
    status: str
    reason: str
    source: Optional[str] = None
    n_features: int = 0
    pit_basis: Optional[str] = None      # how availability is established
    depth_note: Optional[str] = None
    evidence_ref: Optional[str] = None   # prior disposition, if any


@dataclass
class EvidenceVector:
    market: str
    as_of: str
    schema_version: str = SCHEMA_VERSION
    families: dict = field(default_factory=dict)     # family -> FamilyStatus
    values: dict = field(default_factory=dict)       # family -> {feature: value}

    def usable_families(self) -> list[str]:
        return [f for f, s in self.families.items()
                if s["status"] in (AVAILABLE, PARTIAL)]

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "market": self.market,
                "as_of": self.as_of, "families": self.families,
                "values": self.values}


# ── per-family availability probes ────────────────────────────────────
#
# Each probe answers one question: at this as_of, in this market, can this
# family produce a PIT-provable value? Probes read the repository; they never
# fabricate a date.

def _technical(root: Path, market: str, asof: date) -> FamilyStatus:
    """The durable substrate is the SEALED memory-v2 sidecar, not features/.

    This probe originally read features/<market>/<asof>.parquet and reported
    BLOCKED_DATA for every historical date. That was wrong in a specific and
    instructive way: features/ is working state, overwritten and never committed,
    whereas memory-v2 already seals the exact matrix R2 consumed into
    history/<market>/<asof>/technical_features.parquet with its hash inside the
    seal. The evidence existed; the probe was looking in the ephemeral place.

    AVAILABLE therefore requires the SEALED artifact, not merely a file on disk.
    A present-but-unsealed file is BLOCKED_PIT: it cannot prove it is what the
    engine consumed on that day.
    """
    from backend.memory.daily_snapshot import load, verify_seal, snapshot_dir
    a = asof.isoformat()
    snap = load(root, market, a)
    side = snapshot_dir(root, market, a) / "technical_features.parquet"
    if snap is None:
        return FamilyStatus("technical", market, BLOCKED_DATA,
                            "TECHNICAL_MEMORY_MISSING: no sealed day for this as_of; "
                            "what R2 consumed was not recorded and must not be "
                            "recomputed from today's data",
                            source="history/%s/%s/" % (market, a))
    prov = (snap.get("provenance") or {}).get("technical", {})
    if not side.exists():
        return FamilyStatus("technical", market, BLOCKED_DATA,
                            "TECHNICAL_MEMORY_MISSING: day is sealed but carries no "
                            "technical_features sidecar (%s)"
                            % (prov.get("blocked_reason") or "reason not recorded"),
                            source="history/%s/%s/" % (market, a))
    ok, msg = verify_seal(root, market, a)
    if not ok:
        return FamilyStatus("technical", market, BLOCKED_PIT,
                            "sealed matrix fails verification: %s" % msg,
                            source=str(side.relative_to(root).as_posix()))
    if prov.get("pit_status") != "PIT_OK":
        return FamilyStatus("technical", market, BLOCKED_PIT,
                            "sidecar present but provenance is %s: %s"
                            % (prov.get("pit_status"), prov.get("blocked_reason")),
                            source=str(side.relative_to(root).as_posix()))
    return FamilyStatus(
        "technical", market, AVAILABLE,
        "hash-sealed matrix actually consumed by R2 on this as_of",
        source=str(side.relative_to(root).as_posix()),
        n_features=int(prov.get("n_records") or 0),
        pit_basis="memory-v2 seal; sidecar sha256 inside SEALED, verified",
        evidence_ref=(snap.get("sidecars") or {}).get("technical_features.parquet", "")[:16])


def _fundamental(root: Path, market: str, asof: date) -> FamilyStatus:
    """USA has SEC filing dates. India does not, and that is the whole story."""
    if market == "usa":
        p = root / "data/fundamentals/pit/sec_first_known.parquet"
        if p.exists():
            return FamilyStatus(
                "fundamental", market, AVAILABLE,
                "SEC XBRL first-filing values; availability is the observed `filed` date",
                source="data/fundamentals/pit/sec_first_known.parquet",
                pit_basis="observed filing date, median lag 33d from period end",
                depth_note="median 74 quarterly periods / 20 years per company",
                evidence_ref="WS2_SEC_LAKE_V1")
        return FamilyStatus("fundamental", market, BLOCKED_DATA,
                            "SEC lake not acquired in this checkout")
    p = root / "data/raw/india/fundamentals.parquet"
    if not p.exists():
        return FamilyStatus("fundamental", market, BLOCKED_DATA,
                            "no India fundamentals file")
    return FamilyStatus(
        "fundamental", market, BLOCKED_PIT,
        "India fundamentals are a single undated cross-section: 228 rows, no "
        "period_end, no filing_date. The adapter stamps asof=cutoff, so any "
        "historical use assigns today's values to the past",
        source="data/raw/india/fundamentals.parquet",
        pit_basis="NONE — no observation date exists to establish",
        evidence_ref="R3_BUSINESS_TRANSFORMATION_V1")


def _temporal(root: Path, market: str, asof: date) -> FamilyStatus:
    bars = (root / "usa/data/raw/us") if market == "usa" else (root / "data/raw/india")
    n = len(list(bars.glob("*_D1.parquet"))) if bars.exists() else 0
    if n:
        return FamilyStatus("temporal", market, AVAILABLE,
                            "derived from date-indexed bars truncated at cutoff",
                            source=str(bars.relative_to(root).as_posix()),
                            pit_basis="bar dates are observed", n_features=n)
    return FamilyStatus("temporal", market, BLOCKED_DATA, "no price bars")


def _sector(root: Path, market: str, asof: date) -> FamilyStatus:
    from backend.canonical.pit_provenance import sector_asof, PIT_UNAVAILABLE
    m, prov = sector_asof(root, market, asof)
    if m == PIT_UNAVAILABLE:
        return FamilyStatus("sector", market, BLOCKED_PIT,
                            "no committed sector map on or before this date: %s"
                            % prov.get("reason"), pit_basis="git provenance")
    st = FamilyStatus("sector", market, AVAILABLE,
                      "sector map as committed at this date",
                      source=prov.get("source"), n_features=len(m),
                      pit_basis="git commit date %s" % prov.get("commit_date"))
    if market == "india":
        # Recorded honestly: the map exists and is PIT-resolvable, but the
        # production builder misreads it, so R2 never actually saw a sector.
        st.status = PARTIAL
        st.depth_note = ("map is PIT-resolvable, but FeatureBuilder._ticker_sector() "
                         "misreads the flat dict and India sector is 0/228 in every "
                         "snapshot ever built (SECTOR-1/SECTOR-2, reported unfixed)")
    return st


def _peer(root: Path, market: str, asof: date) -> FamilyStatus:
    return FamilyStatus("peer", market, REJECTED,
                        "peer lead/lag produced no FDR-surviving predictive family; "
                        "contemporaneous correlation is descriptive only",
                        evidence_ref="prior disposition — not reopened")


def _cross_sector(root: Path, market: str, asof: date) -> FamilyStatus:
    return FamilyStatus("cross_sector", market, BLOCKED_DATA,
                        "depends on PIT sector plus macro; both unavailable for "
                        "India and macro trend fields are undated for USA")


def _macro(root: Path, market: str, asof: date) -> FamilyStatus:
    if market == "usa":
        p = root / "usa/data/raw/us/macro.parquet"
        if p.exists():
            return FamilyStatus(
                "macro", market, PARTIAL,
                "levels carry real observation dates; derived chg_* trend fields "
                "come from an undated current summary and are withheld historically",
                source="usa/data/raw/us/macro.parquet",
                pit_basis="observed date column, 67 distinct dates")
        return FamilyStatus("macro", market, BLOCKED_DATA, "macro.parquet absent")
    return FamilyStatus("macro", market, BLOCKED_DATA,
                        "India macro source reports/macro_summary.json does not "
                        "exist; the adapter returns 0 rows and stamps asof=cutoff")


def _market_structure(root: Path, market: str, asof: date) -> FamilyStatus:
    from backend.canonical.pit_provenance import universe_asof, PIT_UNAVAILABLE
    u, prov = universe_asof(root, market, asof)
    if u == PIT_UNAVAILABLE:
        return FamilyStatus("market_structure", market, BLOCKED_PIT,
                            "no committed universe on or before this date: %s"
                            % prov.get("reason"))
    return FamilyStatus("market_structure", market, PARTIAL,
                        "universe membership as AEGIS was configured at this date; "
                        "NOT exchange index membership, and no delisting or IPO "
                        "history exists",
                        source=prov.get("source"), n_features=len(u),
                        pit_basis="git commit date %s" % prov.get("commit_date"))


def _exit(root: Path, market: str, asof: date) -> FamilyStatus:
    p = root / "reports" / "context" / ("dynamic_risk_%s.json" % market)
    if p.exists():
        return FamilyStatus("exit", market, PARTIAL,
                            "dynamic-risk sidecar is authoritative for R2 stops, but "
                            "only the current file exists — no per-date history",
                            source=str(p.relative_to(root).as_posix()),
                            pit_basis="single current file, not a series")
    return FamilyStatus("exit", market, BLOCKED_DATA, "no dynamic-risk sidecar")


def _portfolio(root: Path, market: str, asof: date) -> FamilyStatus:
    """Sealed decisions sidecar first; the live lifecycle only for TODAY.

    Same defect as the technical probe had: reports/context/canonical_lifecycle_*
    always holds the LATEST state, so reading it for a past as_of either reports
    the wrong day's portfolio or blocks. memory-v2 seals decisions.parquet
    alongside the feature matrix, which is the durable per-date record.
    """
    from backend.memory.daily_snapshot import load, verify_seal, snapshot_dir
    a = asof.isoformat()
    snap = load(root, market, a)
    side = snapshot_dir(root, market, a) / "decisions.parquet"
    if snap is not None and side.exists():
        ok, msg = verify_seal(root, market, a)
        if not ok:
            return FamilyStatus("portfolio", market, BLOCKED_PIT,
                                "sealed decisions fail verification: %s" % msg,
                                source=str(side.relative_to(root).as_posix()))
        prov = (snap.get("provenance") or {}).get("r2_decision", {})
        if prov.get("pit_status") == "PIT_OK":
            return FamilyStatus(
                "portfolio", market, AVAILABLE,
                "hash-sealed decision state for this as_of",
                source=str(side.relative_to(root).as_posix()),
                n_features=int(prov.get("n_records") or 0),
                pit_basis="memory-v2 seal; decisions sha256 inside SEALED, verified")
        return FamilyStatus("portfolio", market, BLOCKED_PIT,
                            "sealed day carries decisions but provenance is %s: %s"
                            % (prov.get("pit_status"), prov.get("blocked_reason")),
                            source=str(side.relative_to(root).as_posix()))
    # No sealed record. The live file is only admissible when it describes
    # exactly this date - never for a historical one.
    p = root / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    if not p.exists():
        return FamilyStatus("portfolio", market, BLOCKED_DATA, "no lifecycle and no sealed day")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return FamilyStatus("portfolio", market, BLOCKED_DATA, "lifecycle unreadable: %s" % e)
    if str(d.get("asof")) != a:
        return FamilyStatus("portfolio", market, BLOCKED_PIT,
                            "no sealed decisions for %s and the live lifecycle "
                            "describes %s; a past portfolio state cannot be "
                            "recovered from the current file" % (a, d.get("asof")))
    return FamilyStatus("portfolio", market, PARTIAL,
                        "live lifecycle matches this as_of but the day is not sealed",
                        source=str(p.relative_to(root).as_posix()),
                        n_features=len(d.get("current", [])),
                        pit_basis="live file, asof matches; NOT hash-sealed")


_PROBES = {
    "technical": _technical, "fundamental": _fundamental, "temporal": _temporal,
    "sector": _sector, "peer": _peer, "cross_sector": _cross_sector,
    "macro": _macro, "market_structure": _market_structure,
    "exit": _exit, "portfolio": _portfolio,
}


def assemble(root: Path, market: str, asof: date) -> EvidenceVector:
    """Build the vector. Every family is probed; none is assumed."""
    root = Path(root)
    ev = EvidenceVector(market=market, as_of=asof.isoformat())
    for fam in FAMILIES:
        try:
            st = _PROBES[fam](root, market, asof)
        except Exception as e:
            st = FamilyStatus(fam, market, BLOCKED_DATA,
                              "probe failed: %s: %s" % (type(e).__name__, str(e)[:120]))
        ev.families[fam] = asdict(st)
    return ev


def coverage_matrix(root: Path, asof: date, markets=("india", "usa")) -> dict:
    """What can this architecture actually deliver today, per market."""
    out = {"as_of": asof.isoformat(), "schema_version": SCHEMA_VERSION, "markets": {}}
    for m in markets:
        ev = assemble(root, m, asof)
        counts: dict[str, int] = {}
        for f, s in ev.families.items():
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        out["markets"][m] = {
            "families": ev.families,
            "status_counts": counts,
            "usable": ev.usable_families(),
            "n_usable": len(ev.usable_families()),
            "n_families": len(FAMILIES),
        }
    return out


# ── §9 · the replay gate ──────────────────────────────────────────────
#
# One boolean, computed, with every blocker named. It is FALSE by default and
# only becomes TRUE when the evidence for a date can actually be reconstructed
# from sealed artifacts - never because code ran without error.

REQUIRED_FOR_REPLAY = ("technical", "portfolio", "temporal")


def replay_ready(root: Path, market: str, asof: date) -> dict:
    """R3_HISTORICAL_REPLAY_READY for one (market, as_of)."""
    from backend.memory.daily_snapshot import (
        load, verify_seal, check_contract, sha256_of)
    root = Path(root)
    a = asof.isoformat()
    ev = assemble(root, market, asof)
    blockers: list[str] = []

    for fam in REQUIRED_FOR_REPLAY:
        st = ev.families.get(fam, {})
        if st.get("status") not in (AVAILABLE, PARTIAL):
            blockers.append("%s=%s (%s)" % (fam, st.get("status"), st.get("reason", "")[:70]))

    snap = load(root, market, a)
    seal_ok = False
    contract = None
    reconstructible = False
    if snap is None:
        blockers.append("no sealed day for %s %s" % (market, a))
    else:
        seal_ok, msg = verify_seal(root, market, a)
        if not seal_ok:
            blockers.append("seal verification failed: %s" % msg)
        contract = check_contract(snap)
        if contract.get("verdict") != "CONTRACT_MET":
            blockers.append("snapshot contract: %s" % contract.get("verdict"))
        if contract.get("provenance_violations"):
            blockers.append("provenance violations: %d"
                            % len(contract["provenance_violations"]))
        body = {k: snap[k] for k in ("schema_version", "market", "asof", "sealed_utc",
                                     "fingerprints", "sidecars", "provenance", "families")}
        reconstructible = (sha256_of(body) == snap.get("content_hash"))
        if not reconstructible:
            blockers.append("snapshot does not reproduce its own content hash")
        # no future contamination: nothing in the day may postdate the as_of
        for fam, pr in (snap.get("provenance") or {}).items():
            for k in ("observation_date", "publication_date", "effective_date"):
                v = pr.get(k)
                if v and str(v) > a and pr.get("pit_status") == "PIT_OK":
                    blockers.append("%s.%s=%s postdates as_of and is marked PIT_OK"
                                    % (fam, k, v))

    return {
        "schema_version": SCHEMA_VERSION,
        "market": market, "as_of": a,
        "R3_HISTORICAL_REPLAY_READY": not blockers,
        "blockers": blockers,
        "seal_verified": seal_ok,
        "contract": (contract or {}).get("verdict"),
        "hash_reproducible": reconstructible,
        "families": {f: ev.families[f]["status"] for f in FAMILIES},
        "usable_families": ev.usable_families(),
    }

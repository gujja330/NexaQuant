"""USA ticker -> canonical sector, with provenance. CEO 2026-11-04 · Phase 1B.

WHY THIS EXISTS
---------------
`usa/reports/universe.json` carries `sector: "Unknown"` for all 516
names. Not partially populated - entirely absent, which is why the four
`sector_*` features are 0% on USA and why every sector-relative
comparison in the planned Top-300 selector has nothing to stand on.

SEC publishes a SIC code per registrant, free and public. 504 of 516
universe symbols resolve to a CIK and 503 carry a SIC. So the data
exists; what it needs is an honest translation.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not call SIC a GICS sector. SIC is a regulatory filing
classification with one code per registrant and no segment detail, and
some of its codes name a legal structure rather than a business. The
largest single group in our universe is 6798, "Real Estate Investment
Trusts" - 26 companies - where an equity REIT is GICS Real Estate and a
mortgage REIT is GICS Financials, and the SEC record cannot tell them
apart. Those stay UNKNOWN / REVIEW_REQUIRED.

Coverage is not improved by guessing. A classification nobody can
defend is worse than an absent one, because a selector will rank on it.

HISTORY, HONESTLY
-----------------
SEC exposes only the CURRENT classification. There is no `sicHistory`
field, and `formerNames` dates name changes, not reclassifications. So
`first_observed_date` is when AEGIS first saw this classification and
`effective_from` is set equal to it with
`effective_from_basis = FIRST_OBSERVED` - never backdated, never
presented as the date it became true.

`resolve_asof()` therefore returns UNAVAILABLE for any date before the
first observation rather than today's answer wearing a historical date.
That is a smaller claim than a true point-in-time classification, and
the interface is shaped so a licensed PIT provider can later supply
`effective_from_basis = PROVIDER_EFFECTIVE` without changing callers.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# ── mapping methods ────────────────────────────────────────────────
EXACT = "EXACT"        # a 4-digit override · the code names one business
MAPPED = "MAPPED"      # a 2-digit major-group rule
PROXY = "PROXY"        # reserved · no proxy rules enabled today
UNKNOWN = "UNKNOWN"    # no SIC, or a code we refuse to resolve

# ── classification status ──────────────────────────────────────────
CLASSIFIED = "CLASSIFIED"
UNCLASSIFIED = "UNCLASSIFIED"
UNAVAILABLE = "UNAVAILABLE"      # asof precedes our first observation

# ── review status ──────────────────────────────────────────────────
VALIDATED = "VALIDATED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

#: What `effective_from` actually means for this record.
BASIS_FIRST_OBSERVED = "FIRST_OBSERVED"
BASIS_PROVIDER = "PROVIDER_EFFECTIVE"   # reserved for a licensed feed

CONFIG_REL = ("configs", "usa_sic_sector_map.yaml")
STORE_REL = ("data", "classification", "sec_sic.json")


@dataclass(frozen=True)
class SectorClassification:
    """One ticker's resolved sector with full provenance (§C contract)."""
    ticker: str
    source: str
    sic_code: Optional[str]
    sic_description: Optional[str]
    sector: Optional[str]
    mapping_method: str
    confidence: float
    first_observed_date: Optional[str]
    effective_from: Optional[str]
    effective_from_basis: str
    retrieved_at_utc: Optional[str]
    review_status: str
    classification_status: str
    reason: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


class SectorMapConfigError(ValueError):
    """The mapping config is unusable · raised rather than silently empty."""


def _load_yaml(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_config(repo_root: Path) -> dict:
    p = Path(repo_root).joinpath(*CONFIG_REL)
    if not p.exists():
        raise SectorMapConfigError("missing mapping config: %s" % p)
    cfg = _load_yaml(p)
    sectors = set(cfg.get("sectors") or [])
    if not sectors:
        raise SectorMapConfigError("config declares no sectors")
    # Every mapped sector must be in the declared taxonomy. A typo that
    # invented a twelfth sector would produce classifications the
    # sector_* features cannot price.
    bad = []
    for code, entry in (cfg.get("exact") or {}).items():
        s = (entry or {}).get("sector")
        if s not in sectors:
            bad.append("exact[%s]=%r" % (code, s))
    for mg, s in (cfg.get("major_group") or {}).items():
        if s not in sectors:
            bad.append("major_group[%s]=%r" % (mg, s))
    if bad:
        raise SectorMapConfigError(
            "%d mapping(s) name a sector outside the declared taxonomy: %s"
            % (len(bad), ", ".join(bad[:6])))
    return cfg


def load_store(repo_root: Path) -> dict:
    p = Path(repo_root).joinpath(*STORE_REL)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("companies") or {}
    except Exception:
        return {}


def classify_sic(sic_code: Optional[str], sic_description: Optional[str],
                 cfg: dict) -> tuple:
    """(sector, method, confidence, review_status, reason)."""
    if not sic_code:
        return (None, UNKNOWN, 0.0, REVIEW_REQUIRED,
                "no SIC code on the SEC record")
    code = str(sic_code).strip()

    refuse = (cfg.get("review_required") or {}).get(code)
    if refuse is not None:
        return (None, UNKNOWN, 0.0, REVIEW_REQUIRED,
                (refuse.get("reason") or "").strip() or
                "code is listed as unresolvable")

    hit = (cfg.get("exact") or {}).get(code)
    if hit:
        return (hit["sector"], EXACT, 0.9, VALIDATED,
                (hit.get("note") or None))

    mg = code[:2]
    sect = (cfg.get("major_group") or {}).get(mg)
    if sect:
        return (sect, MAPPED, 0.6, VALIDATED,
                "SIC major group %s · no 4-digit override" % mg)

    return (None, UNKNOWN, 0.0, REVIEW_REQUIRED,
            "SIC %s has no exact or major-group rule" % code)


def resolve(repo_root: Path, ticker: str, cfg: Optional[dict] = None,
            store: Optional[dict] = None) -> SectorClassification:
    """Current classification for one ticker."""
    root = Path(repo_root)
    cfg = cfg if cfg is not None else load_config(root)
    store = store if store is not None else load_store(root)
    t = str(ticker).upper().strip()
    rec = store.get(t) or {}
    sic = rec.get("sic_code")
    desc = rec.get("sic_description")
    sector, method, conf, review, reason = classify_sic(sic, desc, cfg)
    first = rec.get("first_observed_date")
    return SectorClassification(
        ticker=t,
        source=rec.get("source") or "SEC:submissions",
        sic_code=sic,
        sic_description=desc,
        sector=sector,
        mapping_method=method,
        confidence=conf,
        first_observed_date=first,
        # effective_from == first_observed_date, and the basis says so.
        # SEC publishes no SIC history, so any earlier date would be an
        # invention.
        effective_from=first,
        effective_from_basis=BASIS_FIRST_OBSERVED,
        retrieved_at_utc=rec.get("retrieved_at_utc"),
        review_status=review,
        classification_status=(CLASSIFIED if sector else UNCLASSIFIED),
        reason=reason if not sector else reason,
    )


def resolve_asof(repo_root: Path, ticker: str, asof: date,
                 cfg: Optional[dict] = None,
                 store: Optional[dict] = None) -> SectorClassification:
    """Classification as AEGIS could have known it on `asof`.

    Before the first observation this returns UNAVAILABLE with no
    sector. It does NOT backdate the current classification, because
    SEC publishes no history and a company's business five years ago may
    not be its business today - the exact lookahead that would
    contaminate sector-relative strength and valuation comparisons.
    """
    cur = resolve(repo_root, ticker, cfg, store)
    first = cur.first_observed_date
    if first and str(asof) >= str(first):
        return cur
    from dataclasses import replace
    return replace(
        cur, sector=None, mapping_method=UNKNOWN, confidence=0.0,
        classification_status=UNAVAILABLE, review_status=REVIEW_REQUIRED,
        reason=("asof %s precedes the first AEGIS observation (%s) · SEC "
                "publishes no SIC history, so the classification for that "
                "date is unavailable rather than assumed"
                % (asof, first or "never observed")))


def resolve_many(repo_root: Path, tickers: Iterable[str]) -> dict:
    root = Path(repo_root)
    cfg, store = load_config(root), load_store(root)
    return {str(t).upper(): resolve(root, t, cfg, store) for t in tickers}


def coverage_report(repo_root: Path, tickers: Iterable[str]) -> dict:
    """Exact / mapped / proxy / unknown counts · never conflated."""
    res = resolve_many(repo_root, tickers)
    n = len(res)
    by_method, by_sector, by_review = {}, {}, {}
    for r in res.values():
        by_method[r.mapping_method] = by_method.get(r.mapping_method, 0) + 1
        by_review[r.review_status] = by_review.get(r.review_status, 0) + 1
        if r.sector:
            by_sector[r.sector] = by_sector.get(r.sector, 0) + 1
    n_class = sum(1 for r in res.values() if r.sector)
    unresolved = sorted(t for t, r in res.items() if not r.sector)
    return {
        "schema": "aegis.usa.sector_coverage.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_universe": n,
        "n_classified": n_class,
        "classified_pct": round(100.0 * n_class / n, 2) if n else 0.0,
        # EXACT and MAPPED are reported separately · a major-group rule
        # is not the same evidence as a 4-digit override, and counting
        # them together would overstate what is known.
        "by_mapping_method": dict(sorted(by_method.items())),
        "by_review_status": dict(sorted(by_review.items())),
        "by_sector": dict(sorted(by_sector.items())),
        "n_unclassified": len(unresolved),
        "unclassified": unresolved[:40],
    }

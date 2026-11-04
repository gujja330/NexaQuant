"""The one place that knows the shape of a ticker→sector mapping.

CEO 2026-11-04 · Phase 1A.

THE DEFECT THIS REPLACES
------------------------
`india/sectors.py` exports a FLAT map:

    SECTORS = {"HDFCBANK": "Financials", "TCS": "IT", ...}
    228 tickers · 17 sectors

Four consumers read it correctly as ticker→sector. Two inverted it,
treating it as sector→[tickers] and iterating the VALUE:

    for sec, syms in SECTORS.items():
        for s in syms:          # 'Financials' -> 'F','i','n','a',...
            m[s] = sec          # {'F': 'HDFCBANK', 'i': 'HDFCBANK', ...}

The result was a 30-entry map keyed by single letters. Join rate against
the India universe: 0 of 228. That is why `sector` was 0% populated in
every India snapshot and why all four `sector_*` features were empty -
not missing data, a mapping read backwards. The data was complete the
whole time.

The two offenders were `feature_store/feature_builder.py` and
`feature_store/features/sector.py`: the feature store, which is the one
consumer whose output reaches the snapshot. Meanwhile
`canonical/pit_provenance.py` carried a docstring stating the contract
plainly. So the contract was documented in the repository and the
feature store disagreed with it silently.

This is the alias-drift class: every consumer holding a private copy of
a vocabulary that belongs in one place. The fix is not to correct two
call sites, which leaves the next consumer free to guess again. It is to
have one resolver that VALIDATES the shape and REFUSES a malformed one,
so the same mistake becomes an exception instead of an empty column.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Optional

#: The contract, stated once.
CONTRACT = "ticker -> sector · FLAT · values are sector-name strings"

#: Suffixes an India ticker may carry in different layers.
_SUFFIXES = (".NS", ".BO")


class MalformedSectorMap(ValueError):
    """Raised when a mapping does not satisfy CONTRACT.

    Deliberately an exception rather than a silent `{}`. The original
    bug produced a wrong-but-plausible map and every downstream check
    passed; an empty column is far harder to notice than a traceback.
    """


def normalize_ticker(ticker: str) -> str:
    """`AARTIIND.NS` -> `AARTIIND`. Layer-agnostic lookup key."""
    t = str(ticker or "").strip().upper()
    for suf in _SUFFIXES:
        if t.endswith(suf):
            return t[: -len(suf)]
    return t


def validate_flat_map(raw: Mapping) -> dict:
    """Return a validated ticker→sector dict, or raise.

    Rejects the inverted shape explicitly, because that is the mistake
    this module exists to prevent.
    """
    if not isinstance(raw, Mapping):
        raise MalformedSectorMap(
            "expected a mapping, got %s · %s" % (type(raw).__name__, CONTRACT))
    if not raw:
        raise MalformedSectorMap("mapping is empty · " + CONTRACT)

    inverted = [k for k, v in raw.items()
                if isinstance(v, (list, tuple, set, frozenset))]
    if inverted:
        raise MalformedSectorMap(
            "mapping is INVERTED (sector -> tickers): %d key(s) hold a "
            "collection, e.g. %r. %s"
            % (len(inverted), inverted[0], CONTRACT))

    bad_type = [k for k, v in raw.items() if not isinstance(v, str)]
    if bad_type:
        raise MalformedSectorMap(
            "%d value(s) are not sector-name strings, e.g. %r -> %r · %s"
            % (len(bad_type), bad_type[0], raw[bad_type[0]], CONTRACT))

    blank = [k for k, v in raw.items() if not v.strip()]
    if blank:
        raise MalformedSectorMap(
            "%d ticker(s) map to a blank sector, e.g. %r · a blank sector "
            "is not a classification" % (len(blank), blank[0]))

    # A flat map has far more tickers than sectors. If the ratio inverts,
    # the caller has almost certainly handed us a sector->ticker map that
    # happens to carry string values.
    n_keys = len(raw)
    n_sectors = len({v.strip() for v in raw.values()})
    if n_keys > 1 and n_sectors >= n_keys:
        raise MalformedSectorMap(
            "%d keys but %d distinct values · a ticker->sector map has "
            "many tickers per sector, so this is probably reversed · %s"
            % (n_keys, n_sectors, CONTRACT))

    return {normalize_ticker(k): v.strip() for k, v in raw.items()}


def india_ticker_sector(repo_root: Optional[Path] = None) -> dict:
    """The validated India ticker→sector map.

    Raises MalformedSectorMap if `india/sectors.py` stops satisfying the
    contract, rather than returning a partial map that reads as missing
    data downstream.
    """
    import sys
    if repo_root is not None:
        rp = str(Path(repo_root))
        if rp not in sys.path:
            sys.path.insert(0, rp)
    from india.sectors import SECTORS  # type: ignore
    return validate_flat_map(SECTORS)


def sector_for(mapping: Mapping, ticker: str) -> Optional[str]:
    """Suffix-tolerant lookup · accepts `TCS`, `TCS.NS` or `tcs`."""
    if not mapping:
        return None
    return mapping.get(normalize_ticker(ticker)) or None


def coverage(mapping: Mapping, universe: Iterable[str]) -> dict:
    """How much of a universe the mapping actually classifies."""
    uni = [str(t) for t in universe]
    hits = [t for t in uni if sector_for(mapping, t)]
    missing = [t for t in uni if not sector_for(mapping, t)]
    n = len(uni)
    return {
        "n_universe": n,
        "n_classified": len(hits),
        "coverage_pct": round(100.0 * len(hits) / n, 2) if n else 0.0,
        "n_sectors": len({sector_for(mapping, t) for t in hits}),
        "unclassified": sorted(missing)[:20],
        "n_unclassified": len(missing),
    }

"""Macro features · market-level, from ONE canonical series definition.

CEO 2026-11-03 · Phase 1. This module used to carry its own symbol table

    MACRO_SYMBOL_MAP = {"^TNX": "macro_10y", "UUP": "macro_dxy", ...}

and read whatever `canon["macro"]` happened to hold. Two defects followed.

`UUP` is the Invesco DB US Dollar Index Bullish Fund - an ETF. USA's own
data labels it "US Dollar Index (Invesco DB proxy)". Its share price runs
28.96-29.04 while the DXY index runs ~101.7, and `feature_registry`
declares `macro_dxy` with unit "level". So USA served an ETF share price
as an index level: `macro_dxy = 29.0`, which is UUP's close on 2026-10-30.

India's canonical macro source is `reports/macro_summary.json`, which is
UNTRACKED and UNDATED. Untracked means it does not exist on a clean
checkout until step 4 of the orchestrator writes it, so a snapshot built
by any path that skips that step gets zero rows and eight silent nulls -
which is exactly what `features/india/2026-11-03.parquet` carries.
Undated means the adapter must refuse any historical cutoff rather than
stamp today's levels with a past date; measured, `adapt_macro(india,
cutoff=today)` returns 19 rows and `cutoff=2026-11-02` returns 0.

Meanwhile SEVEN TRACKED, DATED series with 2000+ rows each sat in
`data/raw/india/global/` unused. The old docstring here said "India has
no macro parquet yet"; that premise was false.

So the symbol table is gone. `backend.feature_store.macro_series` owns
the definition of every macro feature - source, unit, expected domain,
staleness budget and bounded forward-fill - and this module only joins
the result to the universe. An out-of-domain value is INVALID and
resolves to None; nothing is defaulted, zero-filled or mean-filled.

MACRO IS MARKET-WIDE and is broadcast identically to every ticker. That
is its nature, and it is also why a cross-sectional ranking model sees no
opinion in it however correct the numbers are.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from backend.canonical.schemas import CanonicalDataset
from backend.feature_store import macro_series as _ms

#: Kept for readers who grep for the old name. The mapping it used to
#: hold is now in macro_series.SERIES, and `UUP` is explicitly refused as
#: a source for macro_dxy by macro_series.NOT_AN_INDEX_LEVEL.
MACRO_SYMBOL_MAP_RETIRED = True


def _summary_rows(canon: dict) -> Optional[list]:
    """Rows from the undated macro summary, for the MOVE gap only.

    macro_move has no tracked dated series anywhere in this repository,
    so it is the one feature allowed to come from the summary - and only
    for a current asof, never a historical one.
    """
    ds = canon.get("macro") if canon else None
    rows = getattr(ds, "rows", None)
    return list(rows) if rows else None


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
            asof: date, market_name: str,
            root: Optional[Path] = None) -> dict[str, dict]:
    """Macro features for every ticker in `universe`.

    `root` is the repository root, needed to read the tracked global
    series. When it is not supplied the resolver cannot find them, so the
    features resolve MISSING rather than falling back to the symbol table
    that produced the 29.0 - a silent fallback is how this defect
    survived.
    """
    if root is None:
        return {t: {} for t in universe}

    root = Path(root)
    resolved = _ms.resolve_all(root, asof, summary_rows=_summary_rows(canon))
    values = _ms.feature_values(resolved)
    # Only VALID values are present at all; MISSING / STALE / INVALID are
    # dropped so the column is null rather than carrying a number whose
    # status a downstream reader cannot see.
    market_features = {k: v for k, v in values.items() if v is not None}

    try:
        rep = _ms.quality_report(root, asof, market_name, resolved,
                                 n_universe=len(universe))
        p = _ms.report_path(root, market_name, asof)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass            # the report is evidence, not a precondition

    # Broadcast · identical for every ticker, by construction.
    return {t: dict(market_features) for t in universe}

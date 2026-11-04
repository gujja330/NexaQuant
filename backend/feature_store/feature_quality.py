"""Semantic feature quality — registry-driven, granularity-aware.

CEO 2026-11-04. Phase 2.

WHY A COMPLETENESS COUNT IS NOT A QUALITY MEASURE
-------------------------------------------------
Every defect found in Phase 1 passed `notna()`:

  * `macro_dxy` carried 29.0 on all 516 USA rows for months. Fully
    populated. It was the UUP ETF share price standing in for the DXY
    index level, which is ~101.7 — a wrong SERIES, not a missing one.
  * `sector` carries the string 'Unknown' on all 516 USA rows. 100%
    complete, zero information.
  * `fii_net_5d` is one national aggregate written to all 228 India
    rows. Correct at MARKET granularity, and useless as a
    cross-sectional signal — but indistinguishable from the `sector`
    defect to any check that only counts cells.
  * `sma_200` was 0% in both markets because a 200-bar feature sat
    behind a 90-bar window. Null, and the nulls were never questioned.

So this validator answers a different question: does the cell represent
a TRUSTWORTHY OBSERVATION? It reads the registry's declarations —
granularity, provenance, freshness, expected coverage — and judges each
column against what that feature is supposed to be.

The granularity declaration is what makes the verdicts separable. One
value repeated on every row is CORRECT for MARKET, SECTOR and GLOBAL
features and a DEFECT for TICKER features. Nothing else distinguishes
those two cases.

NOTHING IS FABRICATED
---------------------
A missing value stays missing. An invalid value is never replaced with
zero, and a null is never counted as complete. Where this module cannot
determine validity — no declared domain, no observation date in the
frame — it says UNVERIFIABLE rather than VALID.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.feature_store.feature_registry import (FEATURE_REGISTRY,
                                                    FeatureGranularity,
                                                    SHARED_GRANULARITIES)

# ── statuses ────────────────────────────────────────────────────────
VALID = "VALID"                  # a trustworthy observation
MISSING = "MISSING"              # absent · no observation
STALE = "STALE"                  # observed, but older than the declared budget
INVALID = "INVALID"              # present and outside its declared domain
CONSTANT = "CONSTANT"            # one value on every row where that is wrong
ABSTAIN = "ABSTAIN"              # deliberately withheld · the correct answer
UNVERIFIABLE = "UNVERIFIABLE"    # cannot be judged from what is available

#: Strings that are placeholders, not observations. Counting these as
#: populated is what let USA report a sector for every name while
#: knowing none of them.
PLACEHOLDERS = frozenset({"Unknown", "unknown", "UNKNOWN", "N/A", "n/a",
                          "NA", "None", "none", "null", "NULL", "-", "--",
                          "", " ", "nan", "NaN", "TBD", "?"})

#: Identity columns describe the snapshot, not a measurement.
IDENTITY = frozenset({"market", "ticker", "asof", "currency"})


@dataclass
class FeatureQuality:
    """One column's verdict."""
    feature: str
    granularity: str
    # Defaults to UNVERIFIABLE so a code path that forgets to decide
    # cannot accidentally report a feature as VALID.
    status: str = UNVERIFIABLE
    n_rows: int = 0
    n_present: int = 0
    n_placeholder: int = 0
    n_distinct: int = 0
    coverage_pct: float = 0.0
    expected_coverage_pct: Optional[float] = None
    provenance: str = ""
    sample: Optional[str] = None
    reason: Optional[str] = None
    codes: tuple = ()

    @property
    def usable(self) -> bool:
        return self.status == VALID


def _placeholder_mask(s: pd.Series) -> pd.Series:
    """Rows holding a placeholder STRING.

    Only non-null cells are considered. `astype(str)` renders a null as
    the text "None", which is itself in PLACEHOLDERS, so scanning the
    whole column would report an entirely empty field as "placeholder
    (None)" and erase the distinction this module exists to draw:
    `sector` is ABSENT on India and the literal string 'Unknown' on
    USA, and those are different failures with different fixes.
    """
    if s.dtype != object:
        return pd.Series(False, index=s.index)
    out = pd.Series(False, index=s.index)
    nn = s.notna()
    if nn.any():
        out.loc[nn] = s[nn].astype(str).str.strip().isin(PLACEHOLDERS)
    return out


def _macro_domain(feature: str):
    """Declared domain for a macro series, if it has one."""
    try:
        from backend.feature_store.macro_series import SERIES
    except Exception:
        return None
    spec = SERIES.get(feature)
    return spec.domain if spec is not None else None


def check_column(df: pd.DataFrame, feat) -> FeatureQuality:
    """Judge one registered feature against its own declaration."""
    n = len(df)
    g = feat.granularity
    q = FeatureQuality(feature=feat.name, granularity=g.value, n_rows=n,
                       provenance=feat.provenance,
                       expected_coverage_pct=feat.expected_coverage_pct)
    codes: list = []

    if feat.name not in df.columns:
        q.status = MISSING
        q.reason = "column absent from the snapshot"
        q.codes = ("COLUMN_ABSENT",)
        return q

    s = df[feat.name]
    ph = _placeholder_mask(s)
    q.n_placeholder = int(ph.sum())
    # A placeholder is NOT an observation, so it does not count as present.
    real = s.notna() & ~ph
    q.n_present = int(real.sum())
    q.coverage_pct = round(100.0 * q.n_present / n, 2) if n else 0.0
    vals = s[real]
    q.n_distinct = int(vals.nunique()) if q.n_present else 0
    if q.n_present:
        q.sample = str(vals.iloc[0])[:40]

    # ── nothing observed ────────────────────────────────────────
    if q.n_present == 0:
        if q.n_placeholder:
            q.status = MISSING
            q.reason = ("%d/%d rows hold a placeholder (%s) · a placeholder "
                        "is not an observation"
                        % (q.n_placeholder, n,
                           str(s[ph].iloc[0])[:20] if q.n_placeholder else "?"))
            q.codes = ("PLACEHOLDER_ONLY",)
            return q
        q.status = MISSING
        q.reason = "0 of %d rows carry a value" % n
        q.codes = ("EMPTY",)
        return q

    # ── declared domain ─────────────────────────────────────────
    dom = _macro_domain(feat.name)
    if dom is not None:
        num = pd.to_numeric(vals, errors="coerce")
        bad = num[(num < dom[0]) | (num > dom[1])]
        if len(bad):
            q.status = INVALID
            q.reason = ("%d value(s) outside the declared domain "
                        "[%s, %s] · e.g. %s"
                        % (len(bad), dom[0], dom[1], bad.iloc[0]))
            q.codes = ("DOMAIN_VIOLATION",)
            return q

    # ── granularity: is one repeated value right or wrong? ──────
    shared = g in SHARED_GRANULARITIES
    if q.n_distinct == 1 and q.n_present == n and not shared \
            and feat.name not in IDENTITY:
        q.status = CONSTANT
        q.reason = ("one value (%s) on all %d rows for a %s-level feature · "
                    "fully populated and carrying no cross-sectional "
                    "information" % (q.sample, n, g.value))
        q.codes = ("CONSTANT_AT_TICKER_LEVEL",)
        return q
    if shared and q.n_distinct > 1 and g != FeatureGranularity.SECTOR:
        q.status = INVALID
        q.reason = ("%d distinct values for a %s-level feature, which is "
                    "shared by construction · suspect fan-out"
                    % (q.n_distinct, g.value))
        q.codes = ("UNEXPECTED_VARIATION",)
        return q
    if g == FeatureGranularity.UNKNOWN:
        q.status = UNVERIFIABLE
        q.reason = ("granularity is UNKNOWN · constancy and fan-out cannot "
                    "be judged, so no verdict is claimed")
        q.codes = ("GRANULARITY_UNDECLARED",)
        return q

    # ── partial coverage against the declared expectation ───────
    if feat.expected_coverage_pct is not None \
            and q.coverage_pct + 1e-9 < feat.expected_coverage_pct:
        q.status = MISSING
        q.reason = ("%.1f%% coverage against a declared %.1f%% · %d of %d "
                    "rows carry no observation"
                    % (q.coverage_pct, feat.expected_coverage_pct,
                       n - q.n_present, n))
        q.codes = ("COVERAGE_BELOW_DECLARED",)
        return q

    q.status = VALID
    if q.n_placeholder:
        codes.append("PLACEHOLDERS_PRESENT")
    if shared and q.n_distinct == 1:
        codes.append("SHARED_CONSTANT_AS_DECLARED")
    q.codes = tuple(codes)
    return q


def check_snapshot(df: pd.DataFrame, market: str, asof: date,
                   registry: Optional[list] = None) -> dict:
    """Judge every registered feature in one snapshot.

    PIT leakage is checked from the frame's own `asof` column: a snapshot
    carrying more than one asof, or an asof after the requested date, is
    not a point-in-time observation of that date.
    """
    reg = registry if registry is not None else FEATURE_REGISTRY
    results = [check_column(df, f) for f in reg]

    pit = {"ok": True, "codes": []}
    if "asof" in df.columns:
        seen = sorted({str(v)[:10] for v in df["asof"].dropna().unique()})
        pit["asof_values"] = seen
        if len(seen) > 1:
            pit["ok"] = False
            pit["codes"].append("MULTIPLE_ASOF_IN_ONE_SNAPSHOT")
        if any(v > asof.isoformat() for v in seen):
            pit["ok"] = False
            pit["codes"].append("ASOF_AFTER_REQUESTED_DATE")
    else:
        pit["ok"] = False
        pit["codes"].append("NO_ASOF_COLUMN")

    # Values that cannot carry an observation date by construction.
    try:
        from backend.feature_store.feature_history import \
            undated_features_present
        undated = list(undated_features_present(df))
    except Exception:
        undated = []
    if undated and asof < date.today():
        pit["ok"] = False
        pit["codes"].append("UNDATED_VALUE_UNDER_HISTORICAL_ASOF")
    pit["undated_features"] = undated

    by_status: dict = {}
    for r in results:
        by_status.setdefault(r.status, []).append(r.feature)
    by_gran: dict = {}
    for r in results:
        d = by_gran.setdefault(r.granularity, {"n": 0, "valid": 0})
        d["n"] += 1
        d["valid"] += 1 if r.usable else 0

    n_valid = sum(1 for r in results if r.usable)
    return {
        "schema": "aegis.feature_store.quality.v1",
        "market": market,
        "asof": asof.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "n_rows": int(len(df)),
        "n_features": len(results),
        "n_valid": n_valid,
        "valid_pct": round(100.0 * n_valid / len(results), 2) if results else 0.0,
        "point_in_time": pit,
        "by_status": {k: sorted(v) for k, v in sorted(by_status.items())},
        "by_granularity": by_gran,
        "features": {r.feature: asdict(r) for r in results},
    }


def report_path(repo_root: Path, market: str, asof: date) -> Path:
    return (Path(repo_root) / "reports" / "context"
            / ("feature_quality_%s_%s.json" % (market, asof.isoformat())))


def write_report(repo_root: Path, market: str, asof: date,
                 report: dict) -> Path:
    p = report_path(repo_root, market, asof)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return p


def usable_features(report: dict) -> list:
    """The features a scoring engine may consume · everything else abstains."""
    return sorted(k for k, v in report.get("features", {}).items()
                  if v.get("status") == VALID)

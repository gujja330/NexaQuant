"""One canonical definition of every macro feature: source, unit, domain.

CEO 2026-11-03 · Phase 1 · WHAT WAS WRONG, AND IT WAS TWO DIFFERENT THINGS
--------------------------------------------------------------------------
USA `macro_dxy` read 29.0 while the DXY index was 101.73, and India's
scoring snapshot carried 0 of 8 macro fields. Those are not the same bug.

USA · WRONG SOURCE SERIES. `features/macro.py` mapped the yfinance symbol
`UUP` to `macro_dxy`. UUP is the Invesco DB US Dollar Index Bullish Fund,
an ETF; `usa/data/raw/us/macro.parquet` labels it, in its own data,
"US Dollar Index (Invesco DB proxy)". Its close runs 28.96-29.04 while
the DXY index runs ~101.7, and `feature_registry` declares `macro_dxy`
with unit "level". So an ETF share price was being served as an index
level. Not a scaling error, not a percentage conversion, not a join
collision, not a stale cache - the wrong series, correctly transformed.
The snapshot's 29.0 is UUP's close on 2026-10-30.

INDIA · WRONG SOURCE, DIFFERENT WAY. `adapt_macro` reads
`reports/macro_summary.json` for India. That file is UNTRACKED, so it
does not exist on a clean checkout until step 4 of the orchestrator
writes it, and any snapshot built by a path that skips that step gets
zero macro rows and eight silent nulls. It is also UNDATED - one
`run_utc` for the whole file, no per-row observation date - which is why
the adapter has a point-in-time refusal branch returning zero rows for
any historical cutoff. Measured: `adapt_macro(india, cutoff=today)`
returns 19 rows; `cutoff=2026-11-02` returns 0, `:pit-refused`.

Meanwhile SEVEN TRACKED, DATED series with 2000+ rows each sit in
`data/raw/india/global/` unused by the feature store. The module's own
docstring said "India has no macro parquet yet". That premise is false.

WHAT THIS MODULE DOES
---------------------
Declares each macro feature once: which symbol it comes from, what unit
it is in, what range a real observation can occupy, and how stale it may
be. Then resolves a value with provenance and a STATUS, where an
out-of-domain number is INVALID rather than a value. A DXY of 28.96
cannot pass as a level again, whatever the symbol table says, because the
domain check does not consult the symbol table.

Forward-fill is BOUNDED and per-feature. A macro level may carry over a
holiday; a one-month change may not be invented. Nothing is fabricated:
missing, stale and invalid all resolve to None with a reason, never to a
default, a zero or a universe mean.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.feature_store.macro_series.v1"

#: Global series live here. The path sits under the India tree for
#: historical reasons and the contents are NOT India-specific - DXY, gold,
#: WTI, the US 10Y and the VIX are global. Both markets read them, which
#: is why this constant exists instead of a per-market path.
GLOBAL_DIR = ("data", "raw", "india", "global")

STATUS_VALID = "VALID"
STATUS_MISSING = "MISSING"
STATUS_STALE = "STALE"
STATUS_INVALID = "INVALID"
STATUS_CONSTANT = "CONSTANT"

#: Statuses that may reach a feature column. Everything else is None.
USABLE = (STATUS_VALID,)

UNIT_INDEX_LEVEL = "index_level"
UNIT_PERCENT = "percent"
UNIT_USD = "usd"
UNIT_PCT_CHANGE = "pct_change"


@dataclass(frozen=True)
class SeriesSpec:
    """One macro feature, defined once.

    `domain` is the range a genuine observation can occupy. It is the
    guard that makes the UUP-as-DXY substitution impossible to repeat:
    28.96 is simply not an index level in the 70-130 band, so it is
    INVALID no matter which symbol supplied it.
    """
    feature: str
    source_file: Optional[str]          # under GLOBAL_DIR; None = derived
    unit: str
    domain: tuple                       # (low, high) inclusive
    max_age_days: int                   # older than this is STALE
    ffill_days: int                     # bounded carry-over; 0 = none
    derived_from: Optional[str] = None  # feature this is computed from
    lookback_bars: Optional[int] = None  # for a change feature
    note: str = ""


#: Trading days in a month, for the 1-month change features.
BARS_1M = 21

SERIES: Dict[str, SeriesSpec] = {
    "macro_10y": SeriesSpec(
        feature="macro_10y", source_file="US10Y.parquet",
        unit=UNIT_PERCENT, domain=(0.0, 25.0), max_age_days=5, ffill_days=3,
        note="US 10-year Treasury yield in percent, e.g. 4.89"),
    "macro_dxy": SeriesSpec(
        feature="macro_dxy", source_file="DXY.parquet",
        unit=UNIT_INDEX_LEVEL, domain=(50.0, 200.0), max_age_days=5,
        ffill_days=3,
        note=("US Dollar Index LEVEL, e.g. 101.73. NOT the UUP ETF, whose "
              "share price is ~29 - that substitution is what made this "
              "feature read 29.0, and the domain floor of 50 now refuses "
              "it outright")),
    "macro_gold": SeriesSpec(
        feature="macro_gold", source_file="GOLD.parquet",
        unit=UNIT_USD, domain=(200.0, 20000.0), max_age_days=5, ffill_days=3,
        note="Gold in USD per troy ounce"),
    "macro_wti_oil": SeriesSpec(
        feature="macro_wti_oil", source_file="OIL.parquet",
        unit=UNIT_USD, domain=(-50.0, 400.0), max_age_days=5, ffill_days=3,
        note=("WTI in USD per barrel. The floor is negative on purpose: "
              "WTI settled at -37.63 on 2020-04-20, and a domain that "
              "called that invalid would be wrong about history")),
    "macro_vix": SeriesSpec(
        feature="macro_vix", source_file="USVIX.parquet",
        unit=UNIT_INDEX_LEVEL, domain=(1.0, 200.0), max_age_days=5,
        ffill_days=3, note="CBOE VIX level"),
    "macro_move": SeriesSpec(
        feature="macro_move", source_file=None,
        unit=UNIT_INDEX_LEVEL, domain=(10.0, 500.0), max_age_days=5,
        ffill_days=0,
        note=("MOVE (bond volatility). NO tracked dated series exists for "
              "it in this repository, so it resolves from the undated "
              "macro summary when one is supplied and ABSTAINS otherwise. "
              "Reported as a known gap rather than filled")),
    "macro_10y_chg_1m_pct": SeriesSpec(
        feature="macro_10y_chg_1m_pct", source_file=None,
        unit=UNIT_PCT_CHANGE, domain=(-100.0, 200.0), max_age_days=5,
        ffill_days=0, derived_from="macro_10y", lookback_bars=BARS_1M,
        note="percent change in the 10Y yield over 21 trading days"),
    "macro_vix_chg_1m_pct": SeriesSpec(
        feature="macro_vix_chg_1m_pct", source_file=None,
        unit=UNIT_PCT_CHANGE, domain=(-100.0, 1000.0), max_age_days=5,
        ffill_days=0, derived_from="macro_vix", lookback_bars=BARS_1M,
        note="percent change in the VIX over 21 trading days"),
}

#: Symbols that must NEVER supply macro_dxy. Kept as data so the refusal
#: is auditable rather than an accident of which file was mapped.
NOT_AN_INDEX_LEVEL = {
    "UUP": ("macro_dxy", "Invesco DB US Dollar Index Bullish Fund · an ETF "
                         "share price (~29), not the DXY index level (~101)"),
}


@dataclass
class Resolved:
    """A value and everything needed to defend it."""
    feature: str
    value: Optional[float]
    status: str
    unit: str
    source: Optional[str] = None
    observation_date: Optional[str] = None   # the bar the value came from
    normalized_asof: Optional[str] = None    # the date it was resolved FOR
    age_days: Optional[int] = None
    ffilled_days: int = 0
    transformation: str = "identity"
    reason: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def global_dir(root: Path) -> Path:
    return Path(root).joinpath(*GLOBAL_DIR)


def load_series(root: Path, filename: str) -> Optional[pd.Series]:
    """Close series for one global file, tz-naive and sorted.

    The files are already tz-naive `datetime64[ns]` with a `Date` index and
    no duplicates; this normalises anyway so a re-ingest with a tz or a
    repeated date cannot change the join silently.
    """
    p = global_dir(root) / filename
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    if "close" not in df.columns or df.empty:
        return None
    idx = pd.to_datetime(df.index, errors="coerce")
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass                      # already naive
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=idx)
    s = s[~s.index.isna()]
    # Duplicate observation timestamps: keep the LAST, which is the later
    # revision of the same session rather than the first print.
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.dropna()


def _in_domain(spec: SeriesSpec, v: float) -> bool:
    lo, hi = spec.domain
    return (v == v) and (lo <= float(v) <= hi)


def resolve_level(root: Path, spec: SeriesSpec, asof: date,
                  series: Optional[pd.Series] = None) -> Resolved:
    """Resolve one level feature AS OF `asof`, never after it.

    The cut is `index <= asof`, so a historical replay cannot see a later
    observation. Bounded forward-fill then allows the last bar on or
    before `asof` to stand in for up to `ffill_days` calendar days, which
    covers a weekend or a holiday without inventing a trading session.
    """
    out = Resolved(feature=spec.feature, value=None, status=STATUS_MISSING,
                   unit=spec.unit, normalized_asof=asof.isoformat())
    if spec.source_file is None:
        out.reason = "NO_TRACKED_SERIES_FOR_THIS_FEATURE"
        return out
    out.source = str(Path(*GLOBAL_DIR) / spec.source_file)
    s = load_series(root, spec.source_file) if series is None else series
    if s is None or s.empty:
        out.reason = "SOURCE_MISSING_OR_UNREADABLE"
        return out

    cut = pd.Timestamp(asof)
    visible = s[s.index <= cut]
    if visible.empty:
        out.reason = "NO_OBSERVATION_ON_OR_BEFORE_ASOF"
        return out

    obs_ts = visible.index[-1]
    v = float(visible.iloc[-1])
    age = int((cut - obs_ts).days)
    out.observation_date = str(obs_ts.date())
    out.age_days = age
    out.ffilled_days = max(0, age)

    if not _in_domain(spec, v):
        out.status = STATUS_INVALID
        out.reason = ("VALUE_%.4f_OUTSIDE_DOMAIN_%s_%s"
                      % (v, spec.domain[0], spec.domain[1]))
        return out
    if age > spec.max_age_days:
        out.status = STATUS_STALE
        out.reason = ("OBSERVATION_%s_IS_%dd_OLD_MAX_%d"
                      % (out.observation_date, age, spec.max_age_days))
        return out
    if age > spec.ffill_days:
        out.status = STATUS_STALE
        out.reason = ("CARRY_OVER_%dd_EXCEEDS_FFILL_BUDGET_%d"
                      % (age, spec.ffill_days))
        return out

    out.value = round(v, 4)
    out.status = STATUS_VALID
    return out


def resolve_change(root: Path, spec: SeriesSpec, asof: date,
                   series: Optional[pd.Series] = None) -> Resolved:
    """Percent change over `lookback_bars` TRADING bars, ending at asof.

    Computed from the same tracked history as the level it derives from,
    which is only possible now that a dated source is used. The previous
    source carried a precomputed `chg_1m_pct` with no observation date
    behind it, so it could be neither verified nor replayed.
    """
    out = Resolved(feature=spec.feature, value=None, status=STATUS_MISSING,
                   unit=spec.unit, normalized_asof=asof.isoformat(),
                   transformation="pct_change_%d_bars" % (spec.lookback_bars or 0))
    parent = SERIES.get(spec.derived_from or "")
    if parent is None or parent.source_file is None:
        out.reason = "NO_PARENT_SERIES"
        return out
    out.source = str(Path(*GLOBAL_DIR) / parent.source_file)
    s = load_series(root, parent.source_file) if series is None else series
    if s is None or s.empty:
        out.reason = "SOURCE_MISSING_OR_UNREADABLE"
        return out

    cut = pd.Timestamp(asof)
    visible = s[s.index <= cut]
    n = int(spec.lookback_bars or BARS_1M)
    if len(visible) < n + 1:
        out.reason = "NEEDS_%d_BARS_HAS_%d" % (n + 1, len(visible))
        return out

    obs_ts = visible.index[-1]
    age = int((cut - obs_ts).days)
    out.observation_date = str(obs_ts.date())
    out.age_days = age
    if age > parent.max_age_days:
        out.status = STATUS_STALE
        out.reason = "PARENT_OBSERVATION_%dd_OLD" % age
        return out

    base = float(visible.iloc[-(n + 1)])
    last = float(visible.iloc[-1])
    if base == 0:
        out.reason = "ZERO_BASE"
        return out
    v = 100.0 * (last - base) / base
    if not _in_domain(spec, v):
        out.status = STATUS_INVALID
        out.reason = ("VALUE_%.4f_OUTSIDE_DOMAIN_%s_%s"
                      % (v, spec.domain[0], spec.domain[1]))
        return out
    out.value = round(v, 4)
    out.status = STATUS_VALID
    return out


def resolve_from_summary(spec: SeriesSpec, asof: date,
                         summary_rows: Optional[list],
                         symbol: str) -> Resolved:
    """Last-resort resolution from an UNDATED macro summary.

    Only `macro_move` uses this, because no tracked dated MOVE series
    exists. The result is marked with the summary as its source and
    carries no observation date, because the file does not have one - and
    a feature that cannot say when it was observed must not pretend to.
    A historical asof therefore gets MISSING rather than today's level
    wearing a past date, which is the lookahead the India adapter already
    refuses for the same reason.
    """
    out = Resolved(feature=spec.feature, value=None, status=STATUS_MISSING,
                   unit=spec.unit, normalized_asof=asof.isoformat(),
                   source="macro_summary.json", transformation="undated_snapshot")
    if asof < date.today():
        out.reason = ("UNDATED_SOURCE_CANNOT_SERVE_HISTORICAL_ASOF")
        return out
    for r in (summary_rows or []):
        if str(getattr(r, "symbol", None) or r.get("symbol") or "") != symbol:
            continue
        raw = getattr(r, "close", None)
        if raw is None and isinstance(r, dict):
            raw = r.get("last") or r.get("close")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            out.reason = "NON_NUMERIC_IN_SUMMARY"
            return out
        if not _in_domain(spec, v):
            out.status = STATUS_INVALID
            out.reason = ("VALUE_%.4f_OUTSIDE_DOMAIN_%s_%s"
                          % (v, spec.domain[0], spec.domain[1]))
            return out
        out.value = round(v, 4)
        out.status = STATUS_VALID
        return out
    out.reason = "SYMBOL_%s_NOT_IN_SUMMARY" % symbol
    return out


#: Symbols the summary fallback may supply, per feature.
SUMMARY_SYMBOL = {"macro_move": "^MOVE"}


def resolve_all(root: Path, asof: date,
                summary_rows: Optional[list] = None) -> Dict[str, Resolved]:
    """Every macro feature for one asof, with provenance and status."""
    out: Dict[str, Resolved] = {}
    cache: Dict[str, Optional[pd.Series]] = {}

    def _series(fn: str):
        if fn not in cache:
            cache[fn] = load_series(root, fn)
        return cache[fn]

    for name, spec in SERIES.items():
        if spec.derived_from:
            parent = SERIES[spec.derived_from]
            out[name] = resolve_change(root, spec, asof,
                                       series=_series(parent.source_file)
                                       if parent.source_file else None)
        elif spec.source_file:
            out[name] = resolve_level(root, spec, asof,
                                      series=_series(spec.source_file))
        else:
            out[name] = resolve_from_summary(
                spec, asof, summary_rows, SUMMARY_SYMBOL.get(name, ""))
    return out


def feature_values(resolved: Dict[str, Resolved]) -> Dict[str, Optional[float]]:
    """Only VALID values reach a feature column · everything else is None.

    MISSING, STALE and INVALID all come back as None. None of them is
    substituted with a default, a zero or a mean, because a fabricated
    macro level is indistinguishable downstream from a real one.
    """
    return {k: (r.value if r.status in USABLE else None)
            for k, r in resolved.items()}


def quality_report(root: Path, asof: date, market: str,
                   resolved: Dict[str, Resolved],
                   n_universe: Optional[int] = None) -> dict:
    """Missing vs stale vs invalid vs constant vs valid · never blended.

    `'Unknown'`, a default and an out-of-domain number are not valid
    coverage, so they are counted apart. A single blended "8/8 populated"
    is what let a DXY of 29.0 look like full coverage.
    """
    by_status: Dict[str, list] = {}
    for name, r in resolved.items():
        by_status.setdefault(r.status, []).append(name)
    n = len(resolved)
    valid = by_status.get(STATUS_VALID, [])
    return {
        "engine": ENGINE_ID,
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": str(market).lower(),
        "asof": asof.isoformat(),
        "n_features": n,
        "n_valid": len(valid),
        "valid_pct": round(100.0 * len(valid) / n, 2) if n else 0.0,
        "by_status": {k: sorted(v) for k, v in sorted(by_status.items())},
        "features": {k: r.as_dict() for k, r in sorted(resolved.items())},
        "universe_rows": n_universe,
        "market_wide_note": (
            "Macro is MARKET-WIDE: the same value is joined to every ticker, "
            "so these features carry no cross-sectional information and "
            "cannot differentiate names in a ranking model. That is their "
            "nature, not a defect - but it is why a macro model scored "
            "cross-sectionally will show no directional opinion however "
            "correct these numbers are."),
        "known_gaps": {
            k: v.note for k, v in SERIES.items() if v.source_file is None
            and not v.derived_from},
        "refused_symbols": {k: v[1] for k, v in NOT_AN_INDEX_LEVEL.items()},
    }


def report_path(root: Path, market: str, asof: date) -> Path:
    return (Path(root) / "reports" / "context"
            / ("macro_feature_quality_%s.json" % str(market).lower()))

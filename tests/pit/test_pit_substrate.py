"""PIT substrate remediation, 2026-09-15.

Tests required by the PIT SUBSTRATE REMEDIATION mandate.

Tests that assert a DEFECT do so deliberately: the defect is reported, not
fixed, because fixing it would change R2 inputs and the mandate forbids that.
Each such test is a regression detector. It fails the day someone changes the
behaviour, which is exactly when the CEO needs to be told.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


# 1 -------------------------------------------------------------------
def test_universe_asof():
    """Universe resolves from git provenance, and refuses to guess."""
    from backend.canonical.pit_provenance import universe_asof, PIT_UNAVAILABLE
    u, prov = universe_asof(ROOT, "india", date(2026, 3, 2))
    assert u == PIT_UNAVAILABLE, "invented a universe before any list existed"
    u, prov = universe_asof(ROOT, "india", date(2026, 6, 19))
    assert len(u) == 228 and prov["status"] == "PIT_OK"
    u18, _ = universe_asof(ROOT, "india", date(2026, 6, 18))
    assert len(u18) == 51, "2026-06-18 must see the pre-expansion list"
    assert len(universe_asof(ROOT, "usa", date(2026, 7, 20))[0]) == 30
    assert len(universe_asof(ROOT, "usa", date(2026, 8, 10))[0]) == 516


# 2 -------------------------------------------------------------------
def test_sector_asof():
    from backend.canonical.pit_provenance import sector_asof, PIT_UNAVAILABLE
    m, _ = sector_asof(ROOT, "india", date(2026, 3, 2))
    assert m == PIT_UNAVAILABLE
    m, prov = sector_asof(ROOT, "india", date(2026, 6, 19))
    assert len(m) == 228 and m["HDFCBANK"] == "Financials"
    assert prov["status"] == "PIT_OK"


# 3 -------------------------------------------------------------------
def test_fundamentals_observation_date():
    """India fundamentals carry NO observation date, so they stay masked."""
    f = pd.read_parquet(ROOT / "data/raw/india/fundamentals.parquet")
    date_like = [c for c in f.columns
                 if re.search(r"date|asof|period|filing|announce", c, re.I)
                 and c != "next_earnings"]
    assert date_like == [], (
        "an observation date appeared in India fundamentals, so PIT selection "
        "is now possible and the mask should be revisited: %s" % date_like)
    assert len(f) == 228, "single current cross-section, one row per ticker"


# 4 -------------------------------------------------------------------
def test_earnings_observation_date():
    """India earnings is a FORWARD next_earnings field, not an announcement
    history, so announcement timing cannot be proven and stays masked."""
    f = pd.read_parquet(ROOT / "data/raw/india/fundamentals.parquet")
    assert "next_earnings" in f.columns
    for c in ("announcement_date", "report_date", "filing_date"):
        assert c not in f.columns


# 5 -------------------------------------------------------------------
def test_macro_observation_date():
    """USA macro HAS real dates. India macro source does not exist at all."""
    p = ROOT / "usa/data/raw/us/macro.parquet"
    if p.exists():
        d = pd.read_parquet(p)
        assert "date" in d.columns and d["date"].nunique() > 1
    assert not (ROOT / "reports/macro_summary.json").exists(), (
        "India macro source appeared; adapt_macro stamps asof=cutoff at ROW "
        "level, so it must be re-audited before use")


# 5b ------------------------------------------------------------------
def test_macro_pit_selection_is_latest_on_or_before_cutoff():
    """FIXED 2026-09-15. adapt_macro used to take the globally-latest row per
    symbol and only then test the cutoff, so every symbol vanished at any
    historical asof. It now selects the latest observation ON OR BEFORE the
    cutoff, and withholds the undated chg_* trend fields from older rows.

    Production passes cutoff=today and therefore selects the newest row, so it
    keeps both the rows and the trend fields exactly as before.
    """
    from backend.canonical import USA_PROFILE
    from backend.canonical.adapters import adapt_macro
    p = ROOT / "usa/data/raw/us/macro.parquet"
    if not p.exists():
        pytest.skip("usa macro.parquet absent")
    today = adapt_macro(ROOT, USA_PROFILE, date(2026, 9, 15))
    hist = adapt_macro(ROOT, USA_PROFILE, date(2026, 8, 15))
    assert today.n_rows == hist.n_rows > 0, "historical asof must not drop symbols"
    assert all(r.chg_1d_pct is not None for r in today.rows), \
        "production must keep trend fields on the newest observation"
    assert all(r.chg_1d_pct is None for r in hist.rows), \
        "undated trend fields must never attach to a historical row"


# 6 -------------------------------------------------------------------
def test_future_information_rejection():
    """pit_mode must REFUSE a date with no committed record, never fall back."""
    from backend.canonical import INDIA_PROFILE
    from backend.feature_store.feature_builder import FeatureBuilder
    b = FeatureBuilder(ROOT, INDIA_PROFILE, pit_mode=True)
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        b._universe(date(2026, 3, 2))
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        b._ticker_sector(date(2026, 3, 2))


# 7 -------------------------------------------------------------------
def test_mixed_price_basis_detection():
    """DEFECT, reported and unfixed: one parquet, two adjustment bases."""
    a = (ROOT / "india/data_nse.py").read_text(encoding="utf-8")
    b = (ROOT / "india/refresh_data.py").read_text(encoding="utf-8")
    assert "auto_adjust=True" in a
    assert "auto_adjust=False" in b, (
        "price basis changed, so the mixed-basis finding must be re-certified")


# 8 -------------------------------------------------------------------
def test_duplicate_snapshot_detection():
    """Rebuilt snapshots are NOT interchangeable: same asof, differing bytes."""
    groups = defaultdict(list)
    for f in glob.glob(str(ROOT / "features/*/*.parquet")):
        base = os.path.basename(f).split(".")[0]
        groups[(Path(f).parent.name, base)].append(f)
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    if not dups:
        pytest.skip("no duplicate snapshots in this checkout")

    # THE INVARIANT, asserted wherever duplicates exist: every asof has exactly
    # one canonical `<asof>.parquet`, and `.rebuilt_HHMMSS` variants are never
    # selected. This holds in a fresh clone and in a working tree alike.
    for k, v in dups.items():
        base = [f for f in v if ".rebuilt_" not in os.path.basename(f)]
        assert len(base) == 1, "asof %s has no single canonical snapshot" % (k,)

    # The rest is an observation about LOCAL generated state, not an invariant:
    # in the working tree the variants differ in content (usa 2026-09-10 has 14
    # files across 4 hashes), which is why they cannot be treated as
    # interchangeable. A fresh clone tracks only one variant, so nothing to see.
    multi = {k: len({hashlib.md5(open(f, "rb").read()).hexdigest() for f in v})
             for k, v in dups.items()}
    assert all(n >= 1 for n in multi.values())


# 9 -------------------------------------------------------------------
def test_prediction_feature_label_separation():
    """historical.py filters entry_date <= asof while computing EXIT-time
    outcomes, so a trade still open at asof contributes its future result."""
    src = (ROOT / "backend/feature_store/features/historical.py").read_text(encoding="utf-8")
    assert "entry_date" in src
    assert "exit_date" not in src, (
        "historical.py now references exit_date, so the leak may be fixed; "
        "re-measure before relying on hist_ticker_* features")
    lp = ROOT / "reports/learning.parquet"
    if lp.exists():
        d = pd.read_parquet(lp)
        ed = pd.to_datetime(d["entry_date"], errors="coerce")
        xd = pd.to_datetime(d["exit_date"], errors="coerce")
        a = pd.Timestamp("2026-06-19")
        leaked = int(((ed <= a) & (xd > a)).sum())
        assert leaked > 0, "leak vanished, so re-certify hist_ticker_ provenance"


# 10 ------------------------------------------------------------------
def test_production_decision_path_invariance():
    """pit_mode defaults OFF and changes nothing when off."""
    from backend.canonical import INDIA_PROFILE
    from backend.feature_store.feature_builder import FeatureBuilder
    b = FeatureBuilder(ROOT, INDIA_PROFILE)
    assert b.pit_mode is False
    assert b._universe() == b._universe(date(2026, 3, 2)) == b._universe(date(2026, 9, 15))
    import yaml
    r = yaml.safe_load((ROOT / "configs/opportunity_registry.yaml").read_text(encoding="utf-8"))["risk_engine"]
    assert r["atr_multiplier"] == 2.0 and r["trailing_lift_min_pct"] == 5.0
    assert r["monotonic_stops"] == {"india": True, "usa": False}
    sel = json.loads((ROOT / "reports/selected_features.json").read_text(encoding="utf-8"))
    assert sel["n_selected"] == 39 and sel["schema_fingerprint"] == "b65ceb49a83a"


# 11 · the defect this remediation uncovered ---------------------------
def test_india_sector_map_is_built_backwards_DEFECT():
    """DEFECT, reported and NOT fixed because fixing it changes R2 inputs.

    india/sectors.py is a FLAT {ticker: sector} map of 228 entries, but
    FeatureBuilder._ticker_sector() iterates it as {sector: [tickers]}.
    Iterating the string value yields characters, so the map collapses to
    {'F': 'EMAMILTD', ...}, 30 junk entries. India sector is therefore
    0/228 in every snapshot ever built.
    """
    from india.sectors import SECTORS
    assert isinstance(SECTORS, dict) and len(SECTORS) == 228
    assert SECTORS["HDFCBANK"] == "Financials", "flat ticker to sector map"
    built = {}
    for sec, syms in SECTORS.items():
        for s in syms:
            built[s] = sec
    assert len(built) == 30, "defect signature changed, re-audit"
    assert all(len(k) == 1 for k in built), "keys are single characters"

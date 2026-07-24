"""Sprint B0 · History Quality Validation regression tests."""
from __future__ import annotations
import io
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backend.history_quality import (
    HistoryQualityEngine, run_quality_check, build_comparison,
    FamilyStatus, ReadinessVerdict,
)
from backend.history_quality.validators import (
    check_history_parquet, check_learning_corpus, check_price_universe,
    _weekdays_between,
)
from backend.history_quality.metrics import compute_family_score, aggregate_score


_passed = 0
_failed = 0

def _ok(msg):
    global _passed; _passed += 1
    print(f"  [OK] {msg}")

def _fail(msg, e):
    global _failed; _failed += 1
    print(f"  [FAIL] {msg}: {e}")

def _run(label, fn):
    try:
        fn(); _ok(label)
    except AssertionError as e:
        _fail(label, e)
    except Exception as e:
        _fail(label, e)


# ── scoring ──────────────────────────────────────────────────────

def test_score_missing_file_is_zero():
    assert compute_family_score(exists=False, n_rows=0, n_duplicate_dates=0,
                                    n_missing_trading_days=0, schema_ok=False) == 0


def test_score_perfect_state_is_100():
    s = compute_family_score(exists=True, n_rows=100, n_duplicate_dates=0,
                                 n_missing_trading_days=0, schema_ok=True,
                                 expected_min_rows=10)
    assert s == 100


def test_score_partial_row_credit():
    s = compute_family_score(exists=True, n_rows=5, n_duplicate_dates=0,
                                 n_missing_trading_days=0, schema_ok=True,
                                 expected_min_rows=10)
    assert 60 <= s < 100


def test_score_penalises_duplicates():
    s_clean = compute_family_score(exists=True, n_rows=50, n_duplicate_dates=0,
                                        n_missing_trading_days=0, schema_ok=True)
    s_dupes = compute_family_score(exists=True, n_rows=50, n_duplicate_dates=3,
                                        n_missing_trading_days=0, schema_ok=True)
    assert s_dupes < s_clean


def test_score_penalises_missing_days():
    s_clean = compute_family_score(exists=True, n_rows=50, n_duplicate_dates=0,
                                        n_missing_trading_days=0, schema_ok=True)
    s_gaps  = compute_family_score(exists=True, n_rows=50, n_duplicate_dates=0,
                                        n_missing_trading_days=5, schema_ok=True)
    assert s_gaps < s_clean


def test_score_penalises_bad_schema():
    s_ok  = compute_family_score(exists=True, n_rows=50, n_duplicate_dates=0,
                                     n_missing_trading_days=0, schema_ok=True)
    s_bad = compute_family_score(exists=True, n_rows=50, n_duplicate_dates=0,
                                     n_missing_trading_days=0, schema_ok=False)
    assert s_bad < s_ok


def test_aggregate_score_empty_is_zero():
    assert aggregate_score([]) == 0


def test_aggregate_score_mean_across_families():
    assert aggregate_score([80, 90, 100]) == 90


# ── weekday helper ───────────────────────────────────────────────

def test_weekdays_between_excludes_weekends():
    days = _weekdays_between(date(2026, 7, 20), date(2026, 7, 26))
    for d in days:
        assert d.weekday() < 5, f"weekend leaked: {d}"
    assert len(days) == 5


# ── history-parquet validator ────────────────────────────────────

def test_missing_history_file_is_not_applicable():
    tmp = Path(tempfile.mkdtemp())
    r = check_history_parquet(family="rec", path=tmp / "nope.parquet", market="usa")
    assert r.status == FamilyStatus.NOT_APPLICABLE.value
    assert r.exists is False
    shutil.rmtree(tmp)


def test_populated_history_file_passes():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    from datetime import timedelta
    rows = [{"market": "usa", "asof": (date(2026, 7, 1) + timedelta(days=i)).isoformat()}
              for i in range(0, 20) if (date(2026, 7, 1) + timedelta(days=i)).weekday() < 5]
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    r = check_history_parquet(family="rec", path=tmp, market="usa")
    assert r.status == FamilyStatus.PASS.value
    assert r.n_rows == len(rows)
    assert r.n_duplicate_dates == 0
    shutil.rmtree(tmp.parent)


def test_duplicate_dates_downgrade_to_warn():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    rows = [{"market": "usa", "asof": "2026-07-01"},
              {"market": "usa", "asof": "2026-07-01"},
              {"market": "usa", "asof": "2026-07-02"}]
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    r = check_history_parquet(family="rec", path=tmp, market="usa")
    assert r.status == FamilyStatus.WARN.value
    assert r.n_duplicate_dates >= 1
    shutil.rmtree(tmp.parent)


def test_missing_columns_produce_fail():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    pd.DataFrame([{"foo": 1}]).to_parquet(tmp, index=False)
    r = check_history_parquet(family="rec", path=tmp, market="usa",
                                  required_columns=("market", "asof"))
    assert r.status == FamilyStatus.FAIL.value
    assert r.schema_ok is False
    assert len(r.schema_issues) >= 1
    shutil.rmtree(tmp.parent)


def test_extra_dedupe_keys_allow_multi_row_per_day():
    """factor_library-style family: multiple rows on same date should NOT count
    as duplicates when the natural key includes an extra column like 'factor'."""
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    rows = [
        {"market": "usa", "asof": "2026-07-21", "factor": "oil_wti",  "value": 82.0},
        {"market": "usa", "asof": "2026-07-21", "factor": "vix",      "value": 18.6},
        {"market": "usa", "asof": "2026-07-21", "factor": "gold",     "value": 4011.8},
        {"market": "usa", "asof": "2026-07-22", "factor": "oil_wti",  "value": 83.1},
    ]
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    # Without extra key → all 3 rows on 2026-07-21 look like dupes → WARN
    r_naive = check_history_parquet(family="factor_library", path=tmp, market="usa")
    assert r_naive.n_duplicate_dates >= 1
    # With extra key → each (asof, factor) is unique → PASS
    r_correct = check_history_parquet(family="factor_library", path=tmp, market="usa",
                                          extra_dedupe_keys=("factor",))
    assert r_correct.n_duplicate_dates == 0
    assert r_correct.status == FamilyStatus.PASS.value
    shutil.rmtree(tmp.parent)


def test_market_isolation():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    rows = [{"market": "india", "asof": "2026-07-01"},
              {"market": "usa",   "asof": "2026-07-01"},
              {"market": "usa",   "asof": "2026-07-02"}]
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    r_india = check_history_parquet(family="rec", path=tmp, market="india")
    r_usa   = check_history_parquet(family="rec", path=tmp, market="usa")
    assert r_india.n_rows == 1 and r_usa.n_rows == 2
    shutil.rmtree(tmp.parent)


# ── learning corpus ──────────────────────────────────────────────

def test_missing_corpus_is_not_applicable():
    tmp = Path(tempfile.mkdtemp()) / "c.parquet"
    r = check_learning_corpus(path=tmp, market="usa")
    assert r.status == FamilyStatus.NOT_APPLICABLE.value


def test_populated_corpus_passes():
    tmp = Path(tempfile.mkdtemp()) / "c.parquet"
    rows = [{"market": "usa", "ticker": f"T{i}", "rec_asof": "2026-06-01",
                "return_pct": 1.5} for i in range(10)]
    pd.DataFrame(rows).to_parquet(tmp, index=False)
    r = check_learning_corpus(path=tmp, market="usa")
    assert r.status == FamilyStatus.PASS.value
    assert r.n_rows == 10
    shutil.rmtree(tmp.parent)


# ── price universe ───────────────────────────────────────────────

def test_price_universe_missing_dir_fails():
    tmp = Path(tempfile.mkdtemp())
    r = check_price_universe(raw_dir=tmp / "nope", market="usa")
    assert r.status == FamilyStatus.FAIL.value
    shutil.rmtree(tmp)


def test_price_universe_below_min_tickers_fails():
    tmp = Path(tempfile.mkdtemp())
    # Only 2 tickers
    for t in ("AAPL", "MSFT"):
        pd.DataFrame({"close": [100.0, 101.0]},
                        index=pd.to_datetime(["2026-07-20", "2026-07-21"])).to_parquet(
            tmp / f"{t}_D1.parquet"
        )
    r = check_price_universe(raw_dir=tmp, market="usa", required_min_tickers=10)
    assert r.status == FamilyStatus.FAIL.value
    assert r.n_rows == 2
    shutil.rmtree(tmp)


def test_price_universe_healthy_passes():
    tmp = Path(tempfile.mkdtemp())
    from datetime import timedelta
    dates = pd.to_datetime([(date(2026, 6, 1) + timedelta(days=i)).isoformat()
                              for i in range(30) if (date(2026, 6, 1) + timedelta(days=i)).weekday() < 5])
    for i in range(15):
        pd.DataFrame({"close": range(100, 100 + len(dates))}, index=dates).to_parquet(
            tmp / f"T{i}_D1.parquet"
        )
    r = check_price_universe(raw_dir=tmp, market="usa", required_min_tickers=10)
    assert r.status == FamilyStatus.PASS.value
    assert r.n_rows == 15
    shutil.rmtree(tmp)


def test_price_universe_flags_stalled_tickers():
    tmp = Path(tempfile.mkdtemp())
    from datetime import timedelta
    fresh_dates = pd.to_datetime([(date(2026, 7, 1) + timedelta(days=i)).isoformat()
                                     for i in range(20) if (date(2026, 7, 1) + timedelta(days=i)).weekday() < 5])
    stale_dates = pd.to_datetime([(date(2026, 6, 1) + timedelta(days=i)).isoformat()
                                     for i in range(10) if (date(2026, 6, 1) + timedelta(days=i)).weekday() < 5])
    # 12 fresh tickers
    for i in range(12):
        pd.DataFrame({"close": range(100, 100 + len(fresh_dates))}, index=fresh_dates).to_parquet(
            tmp / f"T{i}_D1.parquet"
        )
    # 1 stale ticker (fell way behind)
    pd.DataFrame({"close": range(100, 100 + len(stale_dates))}, index=stale_dates).to_parquet(
        tmp / "STALE_D1.parquet"
    )
    r = check_price_universe(raw_dir=tmp, market="usa", required_min_tickers=10)
    assert r.status in (FamilyStatus.WARN.value, FamilyStatus.FAIL.value)
    assert any("stalled" in n for n in r.notes)
    shutil.rmtree(tmp)


# ── engine end-to-end ────────────────────────────────────────────

def _make_tmp_repo() -> Path:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "reports").mkdir()
    (tmp / "usa" / "reports").mkdir(parents=True)
    (tmp / "data" / "raw" / "india").mkdir(parents=True)
    (tmp / "usa" / "data" / "raw" / "us").mkdir(parents=True)
    return tmp


def test_engine_empty_repo_needs_repair():
    tmp = _make_tmp_repo()
    r = run_quality_check(repo_root=tmp, market="india")
    # No price parquets, no history — verdict must be NEEDS_REPAIR
    assert r.verdict == ReadinessVerdict.NEEDS_REPAIR.value
    assert r.n_fail >= 1     # price family fails when raw_dir is empty
    shutil.rmtree(tmp)


def test_engine_healthy_repo_ready_for_replay():
    tmp = _make_tmp_repo()
    # Seed the two critical families
    from datetime import timedelta
    dates = pd.to_datetime([(date(2026, 6, 1) + timedelta(days=i)).isoformat()
                              for i in range(30) if (date(2026, 6, 1) + timedelta(days=i)).weekday() < 5])
    # Price universe (100 tickers → passes India min-100)
    for i in range(105):
        pd.DataFrame({"close": range(100, 100 + len(dates))}, index=dates).to_parquet(
            tmp / "data" / "raw" / "india" / f"T{i}_D1.parquet"
        )
    # Recommendation history
    rec_rows = [{"market": "india",
                    "asof": (date(2026, 6, 1) + timedelta(days=i)).isoformat(),
                    "n_tickers": 10}
                   for i in range(20) if (date(2026, 6, 1) + timedelta(days=i)).weekday() < 5]
    pd.DataFrame(rec_rows).to_parquet(tmp / "reports" / "recommendation_history.parquet", index=False)

    r = run_quality_check(repo_root=tmp, market="india")
    # Verdict must be at least PARTIAL (many families NOT_APPLICABLE but no FAILs)
    assert r.verdict in (ReadinessVerdict.READY_FOR_REPLAY.value,
                          ReadinessVerdict.PARTIAL.value)
    assert r.n_fail == 0
    shutil.rmtree(tmp)


def test_comparison_builds_from_reports():
    tmp = _make_tmp_repo()
    from backend.history_quality.types import QualityReport
    india = QualityReport(engine="e", version="1", market="india", run_utc="",
                             verdict="READY_FOR_REPLAY", n_families_checked=5,
                             n_pass=3, n_warn=2, n_fail=0, n_not_applicable=0,
                             overall_quality_score=85)
    usa = QualityReport(engine="e", version="1", market="usa", run_utc="",
                           verdict="PARTIAL", n_families_checked=5,
                           n_pass=2, n_warn=3, n_fail=0, n_not_applicable=0,
                           overall_quality_score=70)
    out = tmp / "reports" / "global" / "history_quality_comparison.json"
    payload = build_comparison(india=india, usa=usa, output_path=out)
    assert out.exists()
    assert payload["delta"]["overall_score_usa_minus_india"] == -15
    assert payload["worse_market_overall"] == "usa"
    shutil.rmtree(tmp)


TESTS = [
    ("score: missing file → 0", test_score_missing_file_is_zero),
    ("score: perfect state → 100", test_score_perfect_state_is_100),
    ("score: partial row credit", test_score_partial_row_credit),
    ("score: penalises duplicates", test_score_penalises_duplicates),
    ("score: penalises missing days", test_score_penalises_missing_days),
    ("score: penalises bad schema", test_score_penalises_bad_schema),
    ("aggregate: empty → 0", test_aggregate_score_empty_is_zero),
    ("aggregate: mean of family scores", test_aggregate_score_mean_across_families),
    ("weekdays helper skips weekends", test_weekdays_between_excludes_weekends),
    ("history: missing file → NOT_APPLICABLE", test_missing_history_file_is_not_applicable),
    ("history: populated + clean → PASS", test_populated_history_file_passes),
    ("history: duplicates → WARN", test_duplicate_dates_downgrade_to_warn),
    ("history: missing schema col → FAIL", test_missing_columns_produce_fail),
    ("history: extra dedupe keys allow multi-row-per-day (factor_library)", test_extra_dedupe_keys_allow_multi_row_per_day),
    ("history: market isolation", test_market_isolation),
    ("corpus: missing → NOT_APPLICABLE", test_missing_corpus_is_not_applicable),
    ("corpus: populated → PASS", test_populated_corpus_passes),
    ("price: missing dir → FAIL", test_price_universe_missing_dir_fails),
    ("price: below min tickers → FAIL", test_price_universe_below_min_tickers_fails),
    ("price: healthy fleet → PASS", test_price_universe_healthy_passes),
    ("price: flags stalled tickers", test_price_universe_flags_stalled_tickers),
    ("engine: empty repo → NEEDS_REPAIR", test_engine_empty_repo_needs_repair),
    ("engine: healthy repo → PARTIAL/READY", test_engine_healthy_repo_ready_for_replay),
    ("comparison: delta computed + writes file", test_comparison_builds_from_reports),
]


def main():
    print("=" * 70)
    print("  SPRINT B0 · History Quality Validation · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

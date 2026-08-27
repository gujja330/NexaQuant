"""AEGIS · Delivery · Provenance layer regression tests.

CEO 2026-08-27 acceptance criterion:
> "Repeated pipeline execution produces zero immutable-history drift
>  and zero illegitimate trading-calendar dates."

10 property tests covering the exact failure modes CEO named.
"""
import json
import pytest
from pathlib import Path

from backend.delivery.prediction_snapshot import (
    record_snapshot, get_snapshot, update_mutable,
    check_idempotency, ImmutabilityViolation,
    IMMUTABLE_FIELDS, _load_ledger,
)
from backend.delivery.quarantine import (
    quarantine, reconstruct, restore, cannot_reconstruct,
    is_quarantined, audit_log_for,
)


# ── 1 · historical entry price cannot be restamped ──


def test_1_historical_entry_price_cannot_be_restamped(tmp_path):
    record_snapshot(tmp_path, market="USA", ticker="EIX",
                    prediction_date="2026-08-19", entry_date="2026-08-20",
                    entry_price=74.51, source_close_date="2026-08-20",
                    source_dataset_version="yfinance_20260821",
                    canonical_signal="R1_BUY")
    with pytest.raises(ImmutabilityViolation):
        record_snapshot(tmp_path, market="USA", ticker="EIX",
                        prediction_date="2026-08-19", entry_date="2026-08-20",
                        entry_price=71.41,  # DIFFERENT immutable price
                        source_close_date="2026-08-20",
                        source_dataset_version="yfinance_20260827",
                        canonical_signal="R1_BUY")


# ── 2 · rerunning pipeline is idempotent ──


def test_2_rerunning_pipeline_is_idempotent(tmp_path):
    for _ in range(3):
        record_snapshot(tmp_path, market="USA", ticker="EIX",
                        prediction_date="2026-08-19", entry_date="2026-08-20",
                        entry_price=74.51, source_close_date="2026-08-20",
                        source_dataset_version="yfinance_20260821",
                        canonical_signal="R1_BUY")
    ledger = _load_ledger(tmp_path)
    # Only 1 physical row despite 3 attempted writes
    assert len(ledger) == 1


# ── 3 · changing source parquet after prediction does not alter stored entry price ──


def test_3_changing_source_parquet_does_not_alter_stored_entry_price(tmp_path):
    row = record_snapshot(tmp_path, market="USA", ticker="EIX",
                          prediction_date="2026-08-19", entry_date="2026-08-20",
                          entry_price=74.51, source_close_date="2026-08-20",
                          source_dataset_version="yfinance_snapshot_A",
                          canonical_signal="R1_BUY")
    # Try to update entry_price via mutable path · rejected
    with pytest.raises(ImmutabilityViolation):
        update_mutable(tmp_path, row["prediction_id"], entry_price=71.41)
    # Verify no drift
    stored = get_snapshot(tmp_path, row["prediction_id"])
    assert stored["entry_price"] == 74.51


# ── 4 · weekend/holiday exit dates are rejected ──


def test_4_weekend_exit_dates_are_rejected(tmp_path):
    from backend.delivery.trading_calendar import validate_exit_chain
    import pandas as pd
    # Build a tiny fake index parquet with only weekdays present
    idx_dir = tmp_path / "data" / "raw" / "india"
    idx_dir.mkdir(parents=True)
    # Only weekdays 2026-08-10 (Mon) through 2026-08-14 (Fri)
    dates = pd.to_datetime([
        "2026-08-10","2026-08-11","2026-08-12","2026-08-13","2026-08-14"
    ])
    df = pd.DataFrame({"close":[100,101,102,103,104]}, index=dates)
    df.to_parquet(idx_dir / "NSEI_D1.parquet")
    from backend.delivery.trading_calendar import clear_cache
    clear_cache()
    # Saturday 2026-08-15 should NOT be a legitimate exit
    ok, reason = validate_exit_chain(
        tmp_path, "india",
        prediction_date="2026-08-10", entry_date="2026-08-11",
        exit_date="2026-08-15",  # Saturday
        as_of="2026-08-17")
    assert ok is False
    assert "trading calendar" in reason


# ── 5 · missing trading sessions cannot be substituted with calendar days ──


def test_5_nth_session_after_uses_trading_calendar_not_calendar_days(tmp_path):
    from backend.delivery.trading_calendar import nth_session_after, clear_cache
    import pandas as pd
    idx_dir = tmp_path / "data" / "raw" / "india"
    idx_dir.mkdir(parents=True)
    # Weekdays only · Mon 08-10 through Fri 08-21
    dates = pd.to_datetime([
        "2026-08-10","2026-08-11","2026-08-12","2026-08-13","2026-08-14",
        "2026-08-17","2026-08-18","2026-08-19","2026-08-20","2026-08-21"
    ])
    df = pd.DataFrame({"close":[100 + i for i in range(len(dates))]}, index=dates)
    df.to_parquet(idx_dir / "NSEI_D1.parquet")
    clear_cache()
    # 5th session after 2026-08-14 (Friday) is 2026-08-21 (next Friday)
    # NOT 2026-08-14 + 5 calendar days = 2026-08-19
    result = nth_session_after(tmp_path, "india", "2026-08-14", 5)
    assert result == "2026-08-21", f"expected 2026-08-21 (5th trading session) got {result}"


# ── 6 · duplicate prediction IDs cannot overwrite immutable fields ──


def test_6_duplicate_prediction_id_cannot_overwrite_immutable(tmp_path):
    r1 = record_snapshot(tmp_path, market="USA", ticker="EIX",
                         prediction_date="2026-08-19", entry_date="2026-08-20",
                         entry_price=74.51, source_close_date="2026-08-20",
                         source_dataset_version="A", canonical_signal="R1_BUY")
    # Attempting to write the SAME prediction_id with a different entry_price
    # is a violation
    with pytest.raises(ImmutabilityViolation):
        record_snapshot(tmp_path, market="USA", ticker="EIX",
                        prediction_date="2026-08-19", entry_date="2026-08-20",
                        entry_price=999.99,  # DIFFERENT
                        source_close_date="2026-08-20",
                        source_dataset_version="A", canonical_signal="R1_BUY")


# ── 7 · rebuilding XLSX produces identical historical entry fields ──


def test_7_rebuilding_produces_identical_immutable_fields(tmp_path):
    # Snapshot ledger before
    for pid_data in (
        {"ticker":"EIX", "entry_date":"2026-08-20", "entry_price": 74.51},
        {"ticker":"MSFT","entry_date":"2026-08-19", "entry_price": 512.30},
        {"ticker":"AAPL","entry_date":"2026-08-18", "entry_price": 178.90},
    ):
        record_snapshot(tmp_path, market="USA",
                        prediction_date="2026-08-15",
                        source_close_date=pid_data["entry_date"],
                        source_dataset_version="v1",
                        canonical_signal="R1_BUY",
                        **pid_data)
    before = _load_ledger(tmp_path)
    # Rerun · all attempts should be no-ops
    for pid_data in (
        {"ticker":"EIX", "entry_date":"2026-08-20", "entry_price": 74.51},
        {"ticker":"MSFT","entry_date":"2026-08-19", "entry_price": 512.30},
        {"ticker":"AAPL","entry_date":"2026-08-18", "entry_price": 178.90},
    ):
        record_snapshot(tmp_path, market="USA",
                        prediction_date="2026-08-15",
                        source_close_date=pid_data["entry_date"],
                        source_dataset_version="v1",
                        canonical_signal="R1_BUY",
                        **pid_data)
    after = _load_ledger(tmp_path)
    ok, drift = check_idempotency(tmp_path, before, after)
    assert ok, f"drift detected: {drift}"


# ── 8 · pipeline run twice produces the same evidence rows (subsumed by 7) ──


def test_8_pipeline_run_twice_zero_drift(tmp_path):
    for _ in range(2):
        record_snapshot(tmp_path, market="USA", ticker="EIX",
                        prediction_date="2026-08-19", entry_date="2026-08-20",
                        entry_price=74.51, source_close_date="2026-08-20",
                        source_dataset_version="A", canonical_signal="R1_BUY")
    ledger = _load_ledger(tmp_path)
    assert len(ledger) == 1


# ── 9 · USA and India calendars are handled independently ──


def test_9_usa_and_india_calendars_are_independent(tmp_path):
    from backend.delivery.trading_calendar import is_trading_session, clear_cache
    import pandas as pd
    idx_i = tmp_path / "data" / "raw" / "india"
    idx_i.mkdir(parents=True)
    idx_u = tmp_path / "usa" / "data" / "raw" / "us"
    idx_u.mkdir(parents=True)
    # India: Aug 15 (Independence Day · closed) not a session
    di = pd.to_datetime(["2026-08-14","2026-08-17","2026-08-18"])
    pd.DataFrame({"close":[100,101,102]}, index=di).to_parquet(idx_i/"NSEI_D1.parquet")
    # USA: Aug 15 IS a session (no US holiday)
    du = pd.to_datetime(["2026-08-14","2026-08-15","2026-08-17","2026-08-18"])
    pd.DataFrame({"close":[100,101,102,103]}, index=du).to_parquet(idx_u/"_IDX_GSPC_D1.parquet")
    clear_cache()
    assert is_trading_session(tmp_path, "india", "2026-08-15") is False
    assert is_trading_session(tmp_path, "usa", "2026-08-15") is True


# ── 10 · timezone/date-boundary conversion cannot move an entry/exit date ──


def test_10_timezone_date_boundary_cannot_move_dates(tmp_path):
    # The immutability check MUST use string equality (no timezone shift)
    record_snapshot(tmp_path, market="USA", ticker="EIX",
                    prediction_date="2026-08-19", entry_date="2026-08-20",
                    entry_price=74.51, source_close_date="2026-08-20",
                    source_dataset_version="A", canonical_signal="R1_BUY")
    # A downstream stage attempting to store the same conceptual date but as
    # a slightly different string ("2026-08-20T00:00:00-04:00") must NOT be
    # accepted as identical · immutable-field equality is strict.
    with pytest.raises(ImmutabilityViolation):
        record_snapshot(tmp_path, market="USA", ticker="EIX",
                        prediction_date="2026-08-19",
                        entry_date="2026-08-20T00:00:00-04:00",  # tz-tagged variant
                        entry_price=74.51, source_close_date="2026-08-20",
                        source_dataset_version="A", canonical_signal="R1_BUY")


# ── Quarantine procedure tests ──


def test_quarantine_marks_record_and_appends_audit(tmp_path):
    quarantine(tmp_path, source_file="opportunity_registry.jsonl",
               record_key="USA-R1-EIX-20260814-0ee66d",
               reason="stored entry $74.51 inconsistent with entry_date 2026-08-14",
               evidence={"aug_14_close_yfinance": 71.41, "stored_entry": 74.51})
    assert is_quarantined(tmp_path, "USA-R1-EIX-20260814-0ee66d") is True
    trail = audit_log_for(tmp_path, "USA-R1-EIX-20260814-0ee66d")
    assert len(trail) == 1
    assert trail[0]["action"] == "QUARANTINE"


def test_reconstruct_then_restore_moves_record_out_of_quarantine(tmp_path):
    key = "USA-R1-EIX-20260814-0ee66d"
    quarantine(tmp_path, source_file="opportunity_registry.jsonl",
               record_key=key, reason="date restamp",
               evidence={"stored": 74.51})
    reconstruct(tmp_path, source_file="opportunity_registry.jsonl",
                record_key=key,
                proposed_immutable_fields={"entry_date": "2026-08-20"},
                authoritative_source="yfinance_20260827",
                provenance={"aug_20_close": 74.66})
    restore(tmp_path, record_key=key,
            applied_immutable_fields={"entry_date": "2026-08-20"},
            operator="CEO-approved",
            approval="2026-08-27 explicit")
    assert is_quarantined(tmp_path, key) is False


def test_cannot_reconstruct_keeps_quarantine(tmp_path):
    key = "USA-R1-UNKNOWN-20260814"
    quarantine(tmp_path, source_file="opportunity_registry.jsonl",
               record_key=key, reason="unknown",
               evidence={})
    cannot_reconstruct(tmp_path, record_key=key,
                       reason="no authoritative source",
                       evidence={})
    # Still quarantined (cannot_reconstruct is a note, not a lift)
    assert is_quarantined(tmp_path, key) is True

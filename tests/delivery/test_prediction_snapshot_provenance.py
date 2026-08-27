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


# ─────────────────────────────────────────────────────────────
# CEO 2026-08-27 · canonical/provenance layer end-to-end tests
#
# Reproduces the EXACT two failing USA rows from CI run 33069236589:
#   · I26 · EIX row 11 · Portfolio · entry=$74.51 vs Aug 14 close $71.41
#   · I28 · EA row 175 · Exit History · exit_date=2026-08-26 for delisted ticker
#
# Then asserts the canonical-repair + delivery-wiring path produces
# correct rows on rerun. These are the "exact row" regressions CEO
# explicitly required.
# ─────────────────────────────────────────────────────────────


def test_i26_eix_snapshot_ledger_canonical_repair_produces_correct_entry(tmp_path):
    """Exact reproduction of CI run 33069236589 I26 failure.
    Original EIX snapshot was recorded (in error) at entry_date=Aug 20,
    entry_price=$74.51 · then found to be wrong via source-XLSX and
    yfinance evidence · canonical_repair to entry_date=Aug 14,
    entry_price=$71.08. get_by_ticker(USA, EIX) must return the CORRECTED
    values · not the quarantined originals."""
    from backend.delivery.prediction_snapshot import (
        record_snapshot, apply_canonical_repair, get_by_ticker,
        get_snapshot,
    )
    # Original (wrong) snapshot
    r_old = record_snapshot(tmp_path, market="USA", ticker="EIX",
                             prediction_date="2026-08-19",
                             entry_date="2026-08-20",
                             entry_price=74.51,
                             source_close_date="2026-08-20",
                             source_dataset_version="yfinance_20260827",
                             canonical_signal="R1_BUY")
    old_pid = r_old["prediction_id"]
    # Canonical repair to true values
    fresh = apply_canonical_repair(tmp_path, old_pid,
        new_entry_date="2026-08-14",
        new_entry_price=71.08,
        new_source_close_date="2026-08-14",
        authoritative_source="source XLSX rows 3-7 concordant",
        approval="CEO 2026-08-27")
    assert fresh is not None
    # OLD pid now quarantined via append-only marker
    assert get_snapshot(tmp_path, old_pid) is None, \
        "old wrong snapshot must be quarantined after canonical repair"
    # Delivery consumer's canonical lookup returns the CORRECTED values
    canon = get_by_ticker(tmp_path, "USA", "EIX", "R1_BUY")
    assert canon is not None
    assert canon["entry_date"] == "2026-08-14"
    assert canon["entry_price"] == 71.08, \
        f"delivery consumer must see corrected entry_price=$71.08 · got ${canon['entry_price']}"


def test_i26_eix_delivery_override_prevents_source_xlsx_restamp(tmp_path):
    """When the source XLSX has a corrupted entry_price=$74.51 restamp
    for EIX/R1, but the canonical snapshot ledger has entry_price=$71.08,
    a delivery consumer calling get_by_ticker MUST return $71.08 · this
    is the exact fix wired into scripts/telegram_command_center_send.py."""
    from backend.delivery.prediction_snapshot import (
        record_snapshot, get_by_ticker,
    )
    record_snapshot(tmp_path, market="USA", ticker="EIX",
                    prediction_date="2026-08-13",
                    entry_date="2026-08-14",
                    entry_price=71.08,
                    source_close_date="2026-08-14",
                    source_dataset_version="canonical",
                    canonical_signal="R1_BUY")
    # Simulate what the delivery consumer does · reads source XLSX row
    # (mocked as a tuple) and asks: "canonical snapshot says X override?"
    source_xlsx_row = {
        "ticker": "EIX",
        "entry_price_from_xlsx": 74.51,   # ← corrupted restamp
        "recommended_from_xlsx": "2026-08-14",
        "runner": "R1",
    }
    canon = get_by_ticker(tmp_path, "USA", source_xlsx_row["ticker"],
                          source_xlsx_row["runner"])
    assert canon is not None
    # Delivery consumer override rule
    if isinstance(canon["entry_price"], (int, float)) and canon["entry_price"] > 0:
        source_xlsx_row["entry_price_from_xlsx"] = float(canon["entry_price"])
    assert source_xlsx_row["entry_price_from_xlsx"] == 71.08, \
        "canonical override must replace the corrupted $74.51 with $71.08"


def test_i28_ea_exit_history_uses_repaired_closed_date(tmp_path):
    """Exact reproduction of CI run 33069236589 I28 failure.
    Given a Registry where EA/R2 was closed at 2026-08-26 (fabricated
    orphan closer asof) and then canonically repaired to closed_date=
    2026-08-10 (last-known-evidence), the Exit History synthesizer at
    scripts/telegram_command_center_send.py line 3054-3097 must see the
    REPAIRED closed_date via load_all()'s latest-by-ts_utc rule."""
    from backend.research import opportunity_registry as oreg
    from backend.research.opportunity_registry import make_opportunity_id
    import json
    # Bootstrap Registry with the buggy ORPHAN_AUTO_CLOSE state
    p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    pid = make_opportunity_id("usa", "R2", "EA", "2026-08-11")
    active = {
        "opportunity_id": pid, "market": "usa", "runner": "R2",
        "ticker": "EA", "created_date": "2026-08-11",
        "initial_signal": "BUY", "initial_rank": 1,
        "initial_score": 0.85, "status": "ACTIVE",
        "closed_date": "", "closed_reason": "",
        "last_seen_date": "2026-08-11",
        "ts_utc": "2026-08-20T07:04:20+00:00",
    }
    closed_wrong = dict(active,
        status="CLOSED", closed_date="2026-08-26",
        closed_reason="ORPHAN_AUTO_CLOSE",
        last_seen_date="2026-08-26",
        ts_utc="2026-08-26T17:14:22+00:00")
    with p.open("w", encoding="utf-8") as f:
        f.write(json.dumps(active) + "\n")
        f.write(json.dumps(closed_wrong) + "\n")
    # Apply canonical repair
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10",
        closed_reason="ORPHAN_AUTO_CLOSE · CANONICAL_REPAIR",
        authoritative_source="yfinance",
        approval="CEO 2026-08-27")
    # Simulate the Exit History synthesizer at line 3054-3097
    reg = oreg.load_all(tmp_path)
    synthesized_exit_rows = []
    for opps in reg.values():
        for o in opps:
            if o.market != "usa": continue
            if o.status != "CLOSED": continue
            if not o.closed_date: continue
            synthesized_exit_rows.append({
                "ticker": o.ticker, "runner": o.runner,
                "closed_date": o.closed_date,
                "closed_reason": o.closed_reason,
            })
    ea_rows = [r for r in synthesized_exit_rows if r["ticker"] == "EA"]
    assert len(ea_rows) == 1
    # Exact-row assertion · closed_date == 2026-08-10 (repaired)
    assert ea_rows[0]["closed_date"] == "2026-08-10", \
        (f"Exit History synthesizer must use REPAIRED closed_date=2026-08-10 · "
         f"got {ea_rows[0]['closed_date']} · I28 will still FAIL in CI")
    # And the original 2026-08-26 event MUST still be on disk (append-only)
    events_2026_08_26 = 0
    with p.open() as f:
        for ln in f:
            if not ln.strip(): continue
            r = json.loads(ln)
            if r.get("opportunity_id") == pid and \
                    r.get("closed_date") == "2026-08-26":
                events_2026_08_26 += 1
    assert events_2026_08_26 >= 1, \
        "original 2026-08-26 event was silently overwritten · violates append-only"


def test_i26_i28_rerun_produces_identical_rows(tmp_path):
    """CEO invariant: 'Re-running the pipeline must produce the same row.'
    After canonical repair, re-invoking the repair APIs with the same
    inputs is a NO-OP · Registry event count for repair values stays 1 ·
    snapshot ledger new-pid count stays 1."""
    from backend.delivery.prediction_snapshot import (
        record_snapshot, apply_canonical_repair, _load_ledger,
    )
    from backend.research import opportunity_registry as oreg
    from backend.research.opportunity_registry import make_opportunity_id
    import json
    # EIX snapshot repair
    r_old = record_snapshot(tmp_path, market="USA", ticker="EIX",
                             prediction_date="2026-08-19",
                             entry_date="2026-08-20",
                             entry_price=74.51,
                             source_close_date="2026-08-20",
                             source_dataset_version="wrong",
                             canonical_signal="R1_BUY")
    old_pid = r_old["prediction_id"]
    apply_canonical_repair(tmp_path, old_pid,
        new_entry_date="2026-08-14", new_entry_price=71.08,
        new_source_close_date="2026-08-14",
        authoritative_source="src", approval="CEO")
    ledger_after_first = len(_load_ledger(tmp_path))
    # Re-run
    apply_canonical_repair(tmp_path, old_pid,
        new_entry_date="2026-08-14", new_entry_price=71.08,
        new_source_close_date="2026-08-14",
        authoritative_source="src", approval="CEO")
    ledger_after_second = len(_load_ledger(tmp_path))
    assert ledger_after_second == ledger_after_first, \
        f"snapshot ledger grew on rerun · not idempotent · " \
        f"{ledger_after_first} → {ledger_after_second}"
    # EA Registry repair
    p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    pid = make_opportunity_id("usa", "R2", "EA", "2026-08-11")
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "opportunity_id": pid, "market": "usa", "runner": "R2",
            "ticker": "EA", "created_date": "2026-08-11",
            "initial_signal": "BUY", "initial_rank": None,
            "initial_score": None, "status": "CLOSED",
            "closed_date": "2026-08-26", "closed_reason": "ORPHAN_AUTO_CLOSE",
            "last_seen_date": "2026-08-26",
            "ts_utc": "2026-08-26T17:14:22+00:00",
        }) + "\n")
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="repair",
        authoritative_source="yf", approval="CEO")
    def count_repair_events():
        n = 0
        with p.open() as f:
            for ln in f:
                if not ln.strip(): continue
                r = json.loads(ln)
                if r.get("opportunity_id") == pid and \
                        r.get("closed_date") == "2026-08-10":
                    n += 1
        return n
    n1 = count_repair_events()
    # Rerun
    oreg.apply_canonical_repair(tmp_path, pid,
        closed_date="2026-08-10", closed_reason="repair",
        authoritative_source="yf", approval="CEO")
    n2 = count_repair_events()
    assert n1 == n2, \
        f"Registry repair not idempotent · repair event count grew {n1} → {n2}"


def test_delivery_wire_up_never_touches_canonical_investment_active_json():
    """Every part of the canonical INVESTMENT_ACTIVE JSON emit path in
    scripts/telegram_command_center_send.py must remain byte-identical
    to HEAD after the canonical-snapshot consumer wiring is applied.
    This is CEO's explicit protection for the locked section."""
    import subprocess, tempfile, os
    from pathlib import Path
    # Skip if not in a git repo (test env)
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"],
                       check=True, capture_output=True)
    except Exception:
        import pytest
        pytest.skip("not in a git repo")
    root = Path(__file__).resolve().parents[2]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
    tmp.close()
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "show",
             "HEAD:scripts/telegram_command_center_send.py"],
            capture_output=True)
        with open(tmp.name, "wb") as f: f.write(r.stdout)
        head = open(tmp.name, encoding="utf-8", errors="replace").readlines()
        work = open(root / "scripts/telegram_command_center_send.py",
                    encoding="utf-8").readlines()
        # Verify both real INVESTMENT_ACTIVE emit sections identical
        head_idx = [i for i, l in enumerate(head)
                    if "INVESTMENT_ACTIVE" in l and "canonical" not in l.lower()]
        work_idx = [i for i, l in enumerate(work)
                    if "INVESTMENT_ACTIVE" in l and "canonical" not in l.lower()]
        assert len(head_idx) == len(work_idx), \
            f"INVESTMENT_ACTIVE occurrences count changed · " \
            f"HEAD {len(head_idx)} vs WORK {len(work_idx)}"
        for hi, wi in zip(head_idx, work_idx):
            h_ctx = [l.rstrip() for l in head[max(0,hi-30):hi+30]]
            w_ctx = [l.rstrip() for l in work[max(0,wi-30):wi+30]]
            assert h_ctx == w_ctx, \
                f"INVESTMENT_ACTIVE section around HEAD line {hi+1} " \
                f"differs from WORK line {wi+1}"
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass

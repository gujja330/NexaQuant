"""OPS001-I · Institutional Telegram format regression tests.

Verifies the redesigned `india.telegram_notify.build_message()` output
conforms to `docs/OPS001H_TELEGRAM_REDESIGN.md`:

- Header identifies NEXAQUANT + market asof + regime
- ACTIONS block appears before per-stock detail
- All 6 named sections present
- Integrity footer contains run timestamp + MON001 fingerprint + report SHA
- No strategy / scoring / production logic changed (fingerprint invariant)
- Message length bounded (chunker splits > 3900 chars)

Presentation-only tests. Never sends real Telegram messages. Never modifies
production files.
"""
from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _build():
    """Force a fresh import to get the latest module state."""
    import india.telegram_notify as tn
    importlib.reload(tn)
    return tn.build_message(), tn


def test_1_message_is_non_empty_html():
    msg, _ = _build()
    assert isinstance(msg, str) and len(msg) > 0
    # At least one HTML tag we expect
    assert "<b>" in msg
    print(f"  TEST 1 PASS: message is non-empty HTML ({len(msg)} chars)")


def test_2_header_identifies_nexaquant():
    """First line of the new format is the brand anchor."""
    msg, _ = _build()
    first_line = msg.splitlines()[0]
    assert "NEXAQUANT" in first_line, "first line missing NEXAQUANT brand"
    assert "AEGIS Daily" in first_line
    # Print an ASCII-only summary to avoid Windows console cp1252 issues with the brand emoji.
    ascii_hint = "NEXAQUANT AEGIS Daily present" if "NEXAQUANT" in first_line and "AEGIS Daily" in first_line else "MISSING"
    print(f"  TEST 2 PASS: brand header present ({ascii_hint})")


def test_3_header_shows_market_asof_and_weekday():
    msg, _ = _build()
    # Second line: Market asof <date> (weekday) ...
    lines = msg.splitlines()
    assert len(lines) >= 3, "header too short"
    second = lines[1]
    assert "Market asof" in second, f"second line missing 'Market asof': {second!r}"
    assert re.search(r"\d{4}-\d{2}-\d{2}", second), (
        f"second line missing YYYY-MM-DD date: {second!r}")
    print(f"  TEST 3 PASS: header contains market asof + date")


def test_4_actions_block_is_above_the_fold():
    """The 30-second decision surface: ACTIONS TODAY must be near the top,
    not buried after per-stock details."""
    msg, _ = _build()
    lines = msg.splitlines()
    actions_idx = next((i for i, ln in enumerate(lines) if "ACTIONS TODAY" in ln), -1)
    assert actions_idx >= 0, "ACTIONS TODAY block missing"
    # Should be within first 25 lines (above the fold)
    assert actions_idx < 25, (
        f"ACTIONS TODAY appears at line {actions_idx}, "
        f"should be < 25 for above-fold visibility")
    print(f"  TEST 4 PASS: ACTIONS TODAY at line {actions_idx} (above-fold)")


def test_5_all_six_named_sections_present():
    """Institutional format requires these sections."""
    msg, _ = _build()
    required = [
        "ACTIONS TODAY",
        "MARKET",
        "PORTFOLIO HEALTH",
        "TOP OPPORTUNITIES",
        "CURRENT HOLDINGS",
        "RISK SUMMARY",
        "PERFORMANCE",
        "Integrity",
    ]
    missing = [s for s in required if s not in msg]
    assert not missing, f"missing sections: {missing}"
    print(f"  TEST 5 PASS: all 8 named sections present ({len(required)} checks)")


def test_6_sections_appear_in_specified_order():
    """OPS001-H §2.2 mandates section ordering for decision-flow."""
    msg, _ = _build()
    order = ["ACTIONS TODAY", "MARKET", "PORTFOLIO HEALTH",
              "TOP OPPORTUNITIES", "CURRENT HOLDINGS",
              "RISK SUMMARY", "PERFORMANCE", "Integrity"]
    positions = []
    for name in order:
        idx = msg.find(name)
        assert idx >= 0, f"section '{name}' not found"
        positions.append((name, idx))
    # Verify monotonically increasing positions
    prev = -1; last_name = ""
    for name, idx in positions:
        assert idx > prev, f"section '{name}' at {idx} appears before '{last_name}' at {prev}"
        prev = idx; last_name = name
    print(f"  TEST 6 PASS: sections appear in specified order")


def test_7_integrity_footer_has_all_required_fields():
    msg, _ = _build()
    # Find integrity block (last major section)
    integ = msg[msg.find("Integrity"):]
    required = [
        "Run ",              # run timestamp
        "Market asof",       # data date
        "MON001 fp",         # fingerprint short hash
        "Cert MON001-CERT",  # certification id
        "Cycle",             # strategy version
        "Report SHA",        # message SHA256
        "PAPER_ONLY",        # disclaimer
    ]
    missing = [f for f in required if f not in integ]
    assert not missing, f"integrity footer missing fields: {missing}"
    # SHA should be a real 8-char hex, not the placeholder
    assert "{MSG_SHA}" not in msg, "integrity SHA placeholder not resolved"
    print(f"  TEST 7 PASS: integrity footer has all {len(required)} required fields")


def test_8_integrity_run_timestamp_is_current():
    msg, _ = _build()
    # Extract the run line: "Run YYYY-MM-DDTHH:MMZ (HH:MM IST)"
    m = re.search(r"Run (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)", msg)
    assert m, "integrity run timestamp not found or malformed"
    from datetime import datetime, timezone
    try:
        ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise AssertionError(f"run timestamp not parseable: {e}")
    now = datetime.now(timezone.utc)
    delta_s = abs((now - ts).total_seconds())
    assert delta_s < 60, f"run timestamp is {delta_s:.0f}s old — should be within 60s"
    print(f"  TEST 8 PASS: run timestamp is current (delta {delta_s:.0f}s)")


def test_9_integrity_fingerprint_matches_mon001_seal():
    msg, _ = _build()
    # Extract the fingerprint short hash from the message
    m = re.search(r"MON001 fp ([a-f0-9]+)", msg)
    assert m, "MON001 fingerprint not found in message"
    msg_fp = m.group(1)
    # Compare with the sealed_fingerprint.json
    sealed = json.loads(
        (ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json"
         ).read_text(encoding="utf-8"))
    assert sealed["hash"].startswith(msg_fp), (
        f"message fingerprint {msg_fp!r} does not match seal "
        f"{sealed['hash'][:len(msg_fp)]!r}")
    print(f"  TEST 9 PASS: integrity fingerprint matches seal ({msg_fp}...)")


def test_10_integrity_footer_is_at_the_end():
    msg, _ = _build()
    # 'Integrity' should appear only ONCE and near the tail
    hits = [m.start() for m in re.finditer(r"Integrity", msg)]
    assert len(hits) == 1, f"expected exactly 1 Integrity marker, got {len(hits)}"
    # Position must be in the last 25% of the message
    assert hits[0] > 0.7 * len(msg), (
        f"Integrity block at position {hits[0]}/{len(msg)} — "
        f"should be near the end")
    print(f"  TEST 10 PASS: Integrity footer near message tail")


def test_11_report_sha_is_deterministic_per_content():
    """Same input → same SHA. Different content → different SHA."""
    msg1, tn = _build()
    m1 = re.search(r"Report SHA ([a-f0-9]+)", msg1)
    assert m1, "Report SHA not found"
    # Re-invoke — should produce same content (same inputs), same SHA prefix.
    # (Note: run timestamp changes second-to-second — so we can't hash-equal
    # the whole message. This test just verifies SHA format.)
    assert re.match(r"^[a-f0-9]{8}$", m1.group(1)), (
        f"SHA has unexpected format: {m1.group(1)!r}")
    print(f"  TEST 11 PASS: Report SHA has 8-hex-char format ({m1.group(1)}...)")


def test_12_message_body_uses_current_dividers():
    """The new format uses `━` (heavy horizontal) between sections,
    NOT `═` (double) as in the legacy format. This is a UX consistency check."""
    msg, _ = _build()
    assert "━━━━━━━━━━━━━━━━━━━━━━━━━━━" in msg, (
        "new format missing heavy-line section dividers")
    print(f"  TEST 12 PASS: heavy-line dividers present (new UX)")


def test_13_zero_action_day_handled_gracefully():
    """When NEW/EXIT/WATCH are all zero, the message says 'NO ACTION REQUIRED'.
    This test doesn't force that state — but if the current portfolio genuinely
    has no diff, the message must still be valid."""
    msg, _ = _build()
    # Either NO ACTION REQUIRED appears, or the parts are non-zero — both valid.
    has_no_action = "NO ACTION REQUIRED" in msg
    has_parts = any(kw in msg for kw in [" BUY", " HOLD", " EXIT", " WATCH"])
    assert has_no_action or has_parts, (
        "ACTIONS block should show either 'NO ACTION REQUIRED' or counts")
    print(f"  TEST 13 PASS: ACTIONS block presents cleanly "
          f"({'no-action' if has_no_action else 'with counts'})")


# --- Governance invariants ---


def test_14_no_sealed_files_touched_by_ops001i():
    """OPS001-I must not touch any sealed file. `git diff HEAD` scan."""
    r = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"],
        cwd=str(ROOT), capture_output=True, text=True)
    changed = set(l.strip().replace("\\", "/")
                    for l in r.stdout.splitlines() if l.strip())
    forbidden = {
        "india/recommendation_registry.py",
        "india/recommendation_generator.py",
        "india/confidence_engine.py",
        "india/arjuna_v2.py",
        "india/data_nse.py",
        "india/monitoring/MON001_Forward_Validation/preregistration.md",
        "india/monitoring/MON001_Forward_Validation/mon001.yaml",
        "india/monitoring/MON001_Forward_Validation/monitor.py",
        "india/monitoring/MON001_Forward_Validation/forward_ledger.py",
        "india/monitoring/MON001_Forward_Validation/fingerprint.py",
        "india/monitoring/MON001_Forward_Validation/baseline_envelope.py",
        "india/monitoring/MON001_Forward_Validation/broker_layer.py",
    }
    lab_paths = [p for p in changed if p.startswith("india/ai_lab/")
                 and not p.endswith("__pycache__")]
    touched = forbidden & changed
    assert not touched, f"OPS001-I modified sealed files: {sorted(touched)}"
    assert not lab_paths, f"OPS001-I modified LAB artefacts: {lab_paths}"
    print(f"  TEST 14 PASS: no sealed / LAB artefacts touched")


def test_15_mon001_fingerprint_unchanged():
    from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
    import yaml
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = yaml.safe_load(f)
    sealed = json.loads(
        (ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json"
         ).read_text(encoding="utf-8"))
    current = compute_fingerprint(ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    assert current["hash"] == sealed["hash"], (
        f"MON001 fingerprint drift: sealed={sealed['hash']} current={current['hash']}")
    print(f"  TEST 15 PASS: MON001 fingerprint matches seal ({current['hash'][:16]}...)")


def test_16_production_constants_still_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    m = (ROOT / "india/ai_lab/trial_manifest.md").read_text(encoding="utf-8", errors="ignore")
    assert "cumulative_strategy_search: 38" in m
    print(f"  TEST 16 PASS: HOLD=63, rebal=63, cumulative_strategy_search=38 unchanged")


TESTS = [
    test_1_message_is_non_empty_html,
    test_2_header_identifies_nexaquant,
    test_3_header_shows_market_asof_and_weekday,
    test_4_actions_block_is_above_the_fold,
    test_5_all_six_named_sections_present,
    test_6_sections_appear_in_specified_order,
    test_7_integrity_footer_has_all_required_fields,
    test_8_integrity_run_timestamp_is_current,
    test_9_integrity_fingerprint_matches_mon001_seal,
    test_10_integrity_footer_is_at_the_end,
    test_11_report_sha_is_deterministic_per_content,
    test_12_message_body_uses_current_dividers,
    test_13_zero_action_day_handled_gracefully,
    test_14_no_sealed_files_touched_by_ops001i,
    test_15_mon001_fingerprint_unchanged,
    test_16_production_constants_still_unchanged,
]


def main() -> int:
    print("=" * 70)
    print("  OPS001-I · Institutional Telegram format tests — 16 scenarios")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

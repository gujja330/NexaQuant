"""ENG-follow-up · Telegram reliability tests (2026-07-15).

Verifies the health-check + retry wrapper scripts exist, are structured
correctly, and enforce the delivery-ledger invariants. Does NOT modify
`india/telegram_notify.py` or send real Telegram messages.

Run: python nexaquant/tests/test_telegram_reliability.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


HEALTH_CHECK = ROOT / "scripts" / "telegram_health_check.py"
SEND_RETRY = ROOT / "scripts" / "telegram_send_with_retry.py"
WORKFLOW = ROOT / ".github" / "workflows" / "aegis-daily.yml"


# --- Existence ---


def test_1_health_check_script_exists():
    assert HEALTH_CHECK.exists(), f"missing: {HEALTH_CHECK}"
    text = HEALTH_CHECK.read_text(encoding="utf-8")
    assert "getMe" in text and "getChat" in text
    assert "TELEGRAM_BOT_TOKEN" in text and "TELEGRAM_CHAT_ID" in text
    print("  TEST 1 PASS: telegram_health_check.py exists + references getMe + getChat")


def test_2_send_retry_wrapper_exists():
    assert SEND_RETRY.exists(), f"missing: {SEND_RETRY}"
    text = SEND_RETRY.read_text(encoding="utf-8")
    assert "backoff" in text.lower()
    assert "telegram_delivery_" in text
    assert "SUCCESS_MARKERS" in text and "FAILURE_MARKERS" in text
    print("  TEST 2 PASS: telegram_send_with_retry.py has backoff + markers + ledger path")


def test_3_send_retry_does_not_modify_notify_core():
    """The wrapper must NOT import india.telegram_notify — it invokes it as a
    subprocess so the notify core stays untouched."""
    text = SEND_RETRY.read_text(encoding="utf-8")
    assert "from india.telegram_notify" not in text
    assert "import india.telegram_notify" not in text
    assert "subprocess" in text
    print("  TEST 3 PASS: wrapper uses subprocess (does not import notify core)")


# --- Workflow discipline ---


def test_4_aegis_workflow_has_no_telegram_mask():
    """The Telegram notification step in aegis-daily.yml must NOT have
    `|| echo` or `|| true` masking."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for line in text.splitlines():
        # Look for telegram send lines and ensure they don't mask
        if ("telegram_notify" in line or "telegram_send_with_retry" in line) and \
           line.strip().startswith("run:"):
            assert "|| echo" not in line, (
                f"Telegram send is masked with '|| echo': {line!r}")
            assert "|| true" not in line, (
                f"Telegram send is masked with '|| true': {line!r}")
    print("  TEST 4 PASS: aegis-daily.yml Telegram send is not masked")


def test_5_workflow_calls_health_check_before_send():
    """Health check must appear before the notify step so a stale secret fails
    the workflow before we even try to send."""
    text = WORKFLOW.read_text(encoding="utf-8")
    hc_idx = text.find("telegram_health_check.py")
    send_idx = text.find("telegram_send_with_retry.py")
    assert hc_idx > 0, "telegram_health_check.py not invoked from workflow"
    assert send_idx > 0, "telegram_send_with_retry.py not invoked from workflow"
    assert hc_idx < send_idx, (
        "health check must run BEFORE the send-with-retry step, not after")
    print("  TEST 5 PASS: workflow runs health_check BEFORE send_with_retry")


# --- Behaviour (unit-level, no network) ---


def test_6_send_retry_classifies_success():
    """`_classify` should return SUCCESS on the `sent (N messages)` marker."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("_tswr", SEND_RETRY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    v, mk = m._classify("... sent (2 messages).\n")
    assert v == "SUCCESS" and mk == "sent ("
    print(f"  TEST 6 PASS: _classify('sent (2 messages)') = ({v}, {mk!r})")


def test_7_send_retry_classifies_failures():
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("_tswr2", SEND_RETRY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for stdout in (
        "  cannot send.",
        "  send failed on chunk 1/2: 429",
        "  Telegram API returned not-ok on chunk 1/1.",
        "  MISSING TELEGRAM_BOT_TOKEN/CHAT_ID in .env.telegram",
    ):
        v, mk = m._classify(stdout)
        assert v == "FAILURE", f"expected FAILURE for {stdout!r}, got {v}"
    print("  TEST 7 PASS: _classify catches all 4 failure markers")


def test_8_send_retry_writes_ledger(monkeypatch=None):
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("_tswr3", SEND_RETRY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as tmp:
        # Redirect REPORTS to tmp so we don't pollute real reports/
        m.REPORTS = Path(tmp)
        rec = {"wrapper_ts_start_utc": "2026-07-15T00:00:00+00:00",
                "attempt": 1, "verdict": "SUCCESS"}
        p = m._append_ledger(rec)
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        loaded = json.loads(content.strip().splitlines()[-1])
        assert loaded["verdict"] == "SUCCESS"
    print("  TEST 8 PASS: _append_ledger writes a JSONL row that parses cleanly")


def test_9_health_check_module_imports_cleanly():
    """No syntax error, no top-level side effect."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_thc", HEALTH_CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert hasattr(m, "main")
    print("  TEST 9 PASS: telegram_health_check imports cleanly and defines main()")


def test_10_health_check_exits_1_when_token_missing():
    """When TELEGRAM_BOT_TOKEN is absent from env, script exits 1."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    # Add empty values explicitly to prevent the local .env.telegram loader from
    # populating them from the operator's real env file.
    env["TELEGRAM_BOT_TOKEN"] = ""
    env["TELEGRAM_CHAT_ID"] = ""
    r = subprocess.run([sys.executable, str(HEALTH_CHECK)],
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 1, (
        f"expected exit 1 when TELEGRAM_BOT_TOKEN missing, got {r.returncode}\n"
        f"stdout: {r.stdout}\nstderr: {r.stderr}")
    assert "TELEGRAM_BOT_TOKEN" in r.stdout
    print("  TEST 10 PASS: health check exits 1 when TELEGRAM_BOT_TOKEN missing")


# --- Governance invariants unchanged ---


def test_11_production_constants_still_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg and "rebal=63" in gen
    print("  TEST 11 PASS: HOLD=63, rebal=63 unchanged")


def test_12_telegram_notify_module_healthy():
    """OPS001-I (Telegram redesign) explicitly modified india/telegram_notify.py
    per operator authorization. The earlier "no uncommitted diff" guard from
    the Telegram-reliability phase has been retired. Replaced by an
    import + build_message() smoke test that any future modification
    must preserve.
    """
    import importlib
    import india.telegram_notify as tn
    importlib.reload(tn)
    # Module must have the canonical entry point + it must be callable.
    assert hasattr(tn, "build_message"), "telegram_notify.py must expose build_message()"
    assert callable(tn.build_message), "build_message must be callable"
    # It must be safe to call in a test context (returns a string, not an exception).
    msg = tn.build_message()
    assert isinstance(msg, str) and len(msg) > 0, (
        f"build_message() returned non-string or empty: type={type(msg).__name__}, "
        f"len={len(msg) if isinstance(msg, str) else 'n/a'}")
    print("  TEST 12 PASS: telegram_notify.build_message() import + smoke OK "
          f"({len(msg)} chars)")


def test_13_mon001_fingerprint_still_matches_seal():
    import yaml, json as _json
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = yaml.safe_load(f)
    sealed = _json.loads(
        (ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json")
        .read_text(encoding="utf-8"))
    from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
    current = compute_fingerprint(ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    assert current["hash"] == sealed["hash"], (
        f"CONFIG_DRIFT: current {current['hash']} vs sealed {sealed['hash']}")
    assert current.get("algorithm_version") == 2
    print(f"  TEST 13 PASS: MON001 fingerprint v{current['algorithm_version']} matches seal")


TESTS = [
    test_1_health_check_script_exists,
    test_2_send_retry_wrapper_exists,
    test_3_send_retry_does_not_modify_notify_core,
    test_4_aegis_workflow_has_no_telegram_mask,
    test_5_workflow_calls_health_check_before_send,
    test_6_send_retry_classifies_success,
    test_7_send_retry_classifies_failures,
    test_8_send_retry_writes_ledger,
    test_9_health_check_module_imports_cleanly,
    test_10_health_check_exits_1_when_token_missing,
    test_11_production_constants_still_unchanged,
    test_12_telegram_notify_module_healthy,
    test_13_mon001_fingerprint_still_matches_seal,
]


def main():
    print("=" * 70)
    print("  TELEGRAM RELIABILITY TESTS — 13 scenarios")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
